#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - dependency message
    raise SystemExit("pandas is required. Run this script with the Freqtrade Docker image or the Codex bundled Python.") from exc


DEFAULT_CONFIG: dict[str, Any] = {
    "symbol": "ETH/USDT:USDT",
    "btc_symbol": "BTC/USDT:USDT",
    "data_dir": "user_data/data/okx/futures",
    "database": "user_data/ai_daily_trader_v1.sqlite",
    "timeframes": ["15m", "1h", "4h"],
    "scan_interval_minutes": 1440,
    "account": {
        "wallet_usdt": 1000.0,
    },
    "risk": {
        "risk_per_trade_pct": 1.0,
        "max_leverage": 5.0,
        "max_margin_fraction_per_trade": 0.35,
        "min_confidence": 65,
        "min_rr": 1.8,
        "min_stop_pct": 0.003,
        "max_stop_pct": 0.080,
        "max_entry_deviation_pct": 0.030,
        "allow_countertrend": False,
        "countertrend_min_confidence": 85,
        "countertrend_min_rr": 3.0,
        "min_notional_usdt": 10.0,
    },
    "ai": {
        "api_key_env": "AI_TRADER_API_KEY",
        "base_url_env": "AI_TRADER_BASE_URL",
        "model_env": "AI_TRADER_MODEL",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-reasoner",
        "timeout_seconds": 90,
        "temperature": 0.1,
    },
}


@dataclass
class GateResult:
    passed: bool
    reasons: list[str]
    suggested_order: dict[str, Any] | None


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_CONFIG
    user_config = json.loads(path.read_text(encoding="utf-8"))
    return deep_merge(DEFAULT_CONFIG, user_config)


def resolve_path(path_value: str, base_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_candidate = Path.cwd() / path
    if path.parts and path.parts[0] == "user_data":
        return cwd_candidate
    candidates = [
        base_dir / path,
        cwd_candidate,
        Path("/freqtrade") / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def pair_to_stem(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_").replace("-", "_")


def read_market_file(data_dir: Path, pair: str, timeframe: str, candle_type: str = "futures") -> pd.DataFrame:
    stem = pair_to_stem(pair)
    path = data_dir / f"{stem}-{timeframe}-{candle_type}.feather"
    if not path.exists():
        raise FileNotFoundError(f"Missing market data file: {path}")
    dataframe = pd.read_feather(path)
    dataframe["date"] = pd.to_datetime(dataframe["date"], utc=True)
    dataframe = dataframe.sort_values("date").reset_index(drop=True)
    return dataframe


def read_funding_file(data_dir: Path, pair: str) -> dict[str, Any] | None:
    path = data_dir / f"{pair_to_stem(pair)}-1h-funding_rate.feather"
    if not path.exists():
        return None
    dataframe = pd.read_feather(path)
    if dataframe.empty:
        return None
    dataframe["date"] = pd.to_datetime(dataframe["date"], utc=True)
    dataframe = dataframe.sort_values("date").reset_index(drop=True)
    value_col = "open" if "open" in dataframe.columns else "close"
    series = pd.to_numeric(dataframe[value_col], errors="coerce").dropna()
    if series.empty:
        return None
    latest = float(series.iloc[-1])
    recent = series.tail(7 * 24)
    return {
        "available": True,
        "first": dataframe["date"].iloc[0].isoformat(),
        "last": dataframe["date"].iloc[-1].isoformat(),
        "latest": latest,
        "mean_7d": float(recent.mean()),
        "max_7d": float(recent.max()),
        "min_7d": float(recent.min()),
    }


def add_indicators(dataframe: pd.DataFrame) -> pd.DataFrame:
    df = dataframe.copy()
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce")

    df["ema_20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()
    df["ema_50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()
    df["ema_200"] = close.ewm(span=200, adjust=False, min_periods=200).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, pd.NA)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr_14"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    df["atr_pct"] = df["atr_14"] / close
    df["volume_mean_30"] = volume.rolling(30).mean()
    df["volume_ratio"] = volume / df["volume_mean_30"]
    df["high_20"] = high.rolling(20).max().shift(1)
    df["low_20"] = low.rolling(20).min().shift(1)
    df["high_50"] = high.rolling(50).max().shift(1)
    df["low_50"] = low.rolling(50).min().shift(1)
    df["upper_wick_pct"] = (high - pd.concat([df["open"], close], axis=1).max(axis=1)) / close
    df["lower_wick_pct"] = (pd.concat([df["open"], close], axis=1).min(axis=1) - low) / close
    return df


def pct_change(close: pd.Series, bars: int) -> float | None:
    if len(close) <= bars:
        return None
    old = float(close.iloc[-bars - 1])
    new = float(close.iloc[-1])
    if old == 0:
        return None
    return (new / old) - 1.0


def round_float(value: Any, digits: int = 6) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def summarize_timeframe(dataframe: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    df = add_indicators(dataframe)
    last = df.iloc[-1]
    close = pd.to_numeric(df["close"], errors="coerce")
    window_map = {
        "15m": {"1h": 4, "4h": 16, "24h": 96},
        "1h": {"4h": 4, "24h": 24, "7d": 24 * 7},
        "4h": {"24h": 6, "7d": 6 * 7, "30d": 6 * 30},
    }
    returns = {
        label: round_float(pct_change(close, bars), 6)
        for label, bars in window_map.get(timeframe, {}).items()
    }
    close_value = float(last["close"])
    ema_20 = round_float(last.get("ema_20"))
    ema_50 = round_float(last.get("ema_50"))
    ema_200 = round_float(last.get("ema_200"))
    trend = "neutral"
    if ema_50 and ema_200 and close_value > ema_200 and ema_50 > ema_200:
        trend = "bull"
    elif ema_50 and ema_200 and close_value < ema_200 and ema_50 < ema_200:
        trend = "bear"

    return {
        "timeframe": timeframe,
        "rows": int(len(df)),
        "first": df["date"].iloc[0].isoformat(),
        "last": df["date"].iloc[-1].isoformat(),
        "open": round_float(last.get("open")),
        "high": round_float(last.get("high")),
        "low": round_float(last.get("low")),
        "close": round_float(close_value),
        "returns": returns,
        "trend": trend,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "rsi_14": round_float(last.get("rsi_14"), 3),
        "atr_pct": round_float(last.get("atr_pct"), 6),
        "volume_ratio": round_float(last.get("volume_ratio"), 3),
        "support_20": round_float(last.get("low_20")),
        "resistance_20": round_float(last.get("high_20")),
        "support_50": round_float(last.get("low_50")),
        "resistance_50": round_float(last.get("high_50")),
        "upper_wick_pct": round_float(last.get("upper_wick_pct"), 6),
        "lower_wick_pct": round_float(last.get("lower_wick_pct"), 6),
    }


def classify_regime(symbol_summary: dict[str, Any], btc_summary: dict[str, Any]) -> str:
    target_4h = symbol_summary.get("4h", {})
    btc_4h = btc_summary.get("4h", {})
    target_trend = target_4h.get("trend")
    btc_trend = btc_4h.get("trend")
    target_7d = (target_4h.get("returns") or {}).get("7d")
    btc_7d = (btc_4h.get("returns") or {}).get("7d")
    if target_trend == "bull" and btc_trend == "bull" and (target_7d or 0) > 0 and (btc_7d or 0) > 0:
        return "risk_on_bull"
    if target_trend == "bear" and btc_trend == "bear" and (target_7d or 0) < 0 and (btc_7d or 0) < 0:
        return "risk_off_bear"
    return "mixed_or_range"


def build_snapshot(config: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    data_dir = resolve_path(config["data_dir"], config_dir)
    symbol = config["symbol"]
    btc_symbol = config["btc_symbol"]
    timeframes = config.get("timeframes", ["15m", "1h", "4h"])

    target: dict[str, Any] = {}
    btc: dict[str, Any] = {}
    for timeframe in timeframes:
        target[timeframe] = summarize_timeframe(read_market_file(data_dir, symbol, timeframe), timeframe)
    for timeframe in ["1h", "4h"]:
        btc[timeframe] = summarize_timeframe(read_market_file(data_dir, btc_symbol, timeframe), timeframe)

    latest_price = target["1h"]["close"] if "1h" in target else target[timeframes[-1]]["close"]
    snapshot = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "latest_price": latest_price,
        "market_regime": classify_regime(target, btc),
        "target": target,
        "btc": btc,
        "funding": read_funding_file(data_dir, symbol),
        "data_dir": str(data_dir),
        "notes": [
            "Funding history may be short; do not over-weight it.",
            "No orderbook, liquidation feed, or open-interest feed is included in V1.",
        ],
    }
    return snapshot


def build_prompt(snapshot: dict[str, Any], config: dict[str, Any]) -> str:
    risk = config["risk"]
    schema = {
        "decision": "long | short | no_trade",
        "confidence": "integer 0-100",
        "entry_type": "market | limit | stop | none",
        "entry": "number or null",
        "stop_loss": "number or null",
        "take_profit": "number or null",
        "time_horizon": "intraday | 1-3d | swing | none",
        "reason": "short, data-based reason",
        "invalid_if": "condition that invalidates the idea",
        "key_risks": ["risk 1", "risk 2"],
    }
    return (
        "You are a disciplined crypto futures trading analyst. "
        "Your job is not to force a trade. Choose no_trade unless the provided data shows an asymmetric setup.\n\n"
        "Hard rules:\n"
        f"- Minimum confidence for a tradable plan is {risk['min_confidence']}.\n"
        f"- Minimum reward/risk ratio is {risk['min_rr']}.\n"
        "- Every tradable plan must include entry, stop_loss, and take_profit.\n"
        "- Use only the market snapshot below. Do not invent news, orderbook, liquidation, or open-interest data.\n"
        "- If the setup is unclear, output no_trade.\n"
        "- Return only one JSON object. No markdown, no explanation outside JSON.\n\n"
        f"Required JSON schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"Market snapshot:\n{json.dumps(snapshot, ensure_ascii=False, indent=2)}"
    )


def strip_thinking_and_extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned.strip(), flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def call_ai(prompt: str, config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    ai_config = config["ai"]
    api_key = os.getenv(ai_config["api_key_env"], "").strip()
    if not api_key:
        decision = {
            "decision": "no_trade",
            "confidence": 0,
            "entry_type": "none",
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "time_horizon": "none",
            "reason": f"Missing API key env var {ai_config['api_key_env']}; recorded snapshot only.",
            "invalid_if": "Set the API key and rerun.",
            "key_risks": ["No model call was made."],
        }
        return decision, json.dumps(decision, ensure_ascii=False)

    base_url = os.getenv(ai_config["base_url_env"], ai_config["default_base_url"]).rstrip("/")
    model = os.getenv(ai_config["model_env"], ai_config["default_model"])
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON. Do not include markdown or hidden reasoning.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": float(ai_config.get("temperature", 0.1)),
        "stream": False,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=int(ai_config.get("timeout_seconds", 90))) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI API HTTP {exc.code}: {detail[:500]}") from exc
    parsed = json.loads(raw)
    content = parsed["choices"][0]["message"]["content"]
    return strip_thinking_and_extract_json(content), content


def normalize_decision(decision: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(decision)
    raw = str(normalized.get("decision") or normalized.get("action") or "no_trade").strip().lower()
    mapping = {
        "buy": "long",
        "long": "long",
        "sell": "short",
        "short": "short",
        "wait": "no_trade",
        "hold": "no_trade",
        "none": "no_trade",
        "no trade": "no_trade",
        "no_trade": "no_trade",
    }
    normalized["decision"] = mapping.get(raw, "no_trade")
    normalized["confidence"] = int(float(normalized.get("confidence") or 0))
    normalized["entry_type"] = str(normalized.get("entry_type") or "market").lower()
    if normalized["decision"] == "no_trade":
        normalized["entry_type"] = "none"
    for key in ["entry", "stop_loss", "take_profit"]:
        value = normalized.get(key)
        normalized[key] = round_float(value, 8)
    if "key_risks" not in normalized or not isinstance(normalized["key_risks"], list):
        normalized["key_risks"] = []
    return normalized


def is_countertrend(decision: str, snapshot: dict[str, Any]) -> bool:
    target_trend = snapshot.get("target", {}).get("4h", {}).get("trend")
    btc_trend = snapshot.get("btc", {}).get("4h", {}).get("trend")
    if decision == "long":
        return target_trend == "bear" and btc_trend == "bear"
    if decision == "short":
        return target_trend == "bull" and btc_trend == "bull"
    return False


def risk_gate(decision: dict[str, Any], snapshot: dict[str, Any], config: dict[str, Any]) -> GateResult:
    risk = config["risk"]
    account = config["account"]
    reasons: list[str] = []
    suggested_order: dict[str, Any] | None = None

    side = decision["decision"]
    if side == "no_trade":
        return GateResult(False, ["AI chose no_trade."], None)

    confidence = int(decision.get("confidence") or 0)
    if confidence < int(risk["min_confidence"]):
        reasons.append(f"confidence {confidence} below min {risk['min_confidence']}")

    entry = decision.get("entry")
    stop_loss = decision.get("stop_loss")
    take_profit = decision.get("take_profit")
    if not all(isinstance(x, (int, float)) and x > 0 for x in [entry, stop_loss, take_profit]):
        reasons.append("entry, stop_loss, and take_profit must be positive numbers")
        return GateResult(False, reasons, None)

    latest_price = float(snapshot["latest_price"])
    entry_deviation = abs(float(entry) / latest_price - 1.0)
    if entry_deviation > float(risk["max_entry_deviation_pct"]):
        reasons.append(f"entry deviation {entry_deviation:.2%} is above max {risk['max_entry_deviation_pct']:.2%}")

    if side == "long":
        if not (stop_loss < entry < take_profit):
            reasons.append("long plan must satisfy stop_loss < entry < take_profit")
    elif side == "short":
        if not (take_profit < entry < stop_loss):
            reasons.append("short plan must satisfy take_profit < entry < stop_loss")
    else:
        reasons.append(f"unsupported decision: {side}")

    stop_pct = abs(float(entry) - float(stop_loss)) / float(entry)
    reward_pct = abs(float(take_profit) - float(entry)) / float(entry)
    rr = reward_pct / stop_pct if stop_pct > 0 else 0
    if stop_pct < float(risk["min_stop_pct"]):
        reasons.append(f"stop distance {stop_pct:.2%} below min {risk['min_stop_pct']:.2%}")
    if stop_pct > float(risk["max_stop_pct"]):
        reasons.append(f"stop distance {stop_pct:.2%} above max {risk['max_stop_pct']:.2%}")
    if rr < float(risk["min_rr"]):
        reasons.append(f"reward/risk {rr:.2f} below min {risk['min_rr']}")

    countertrend = is_countertrend(side, snapshot)
    if countertrend and not bool(risk.get("allow_countertrend", False)):
        if confidence < int(risk["countertrend_min_confidence"]) or rr < float(risk["countertrend_min_rr"]):
            reasons.append(
                "countertrend trade rejected unless confidence and reward/risk are exceptionally high"
            )

    wallet = float(account["wallet_usdt"])
    risk_usdt = wallet * float(risk["risk_per_trade_pct"]) / 100.0
    max_leverage = float(risk["max_leverage"])
    max_margin = wallet * float(risk["max_margin_fraction_per_trade"])
    max_notional = max_margin * max_leverage
    notional_by_risk = risk_usdt / stop_pct if stop_pct > 0 else 0.0
    notional = min(notional_by_risk, max_notional)
    if notional < float(risk["min_notional_usdt"]):
        reasons.append(f"notional {notional:.2f} below min {risk['min_notional_usdt']}")

    leverage = max(1.0, math.ceil(notional / max_margin)) if max_margin > 0 else 1.0
    leverage = min(leverage, max_leverage)
    margin = notional / leverage if leverage > 0 else notional
    quantity = notional / float(entry)
    actual_risk_usdt = notional * stop_pct
    actual_risk_pct = actual_risk_usdt / wallet * 100.0 if wallet > 0 else 0.0

    suggested_order = {
        "symbol": snapshot["symbol"],
        "side": side,
        "entry_type": decision.get("entry_type", "market"),
        "entry": round_float(entry, 6),
        "stop_loss": round_float(stop_loss, 6),
        "take_profit": round_float(take_profit, 6),
        "reward_risk": round_float(rr, 3),
        "stop_pct": round_float(stop_pct, 6),
        "notional_usdt": round_float(notional, 3),
        "margin_usdt": round_float(margin, 3),
        "quantity": round_float(quantity, 8),
        "leverage": round_float(leverage, 2),
        "risk_usdt": round_float(actual_risk_usdt, 3),
        "risk_pct_of_wallet": round_float(actual_risk_pct, 3),
        "countertrend": countertrend,
    }
    return GateResult(not reasons, reasons, suggested_order if not reasons else suggested_order)


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            latest_price REAL,
            decision TEXT,
            confidence INTEGER,
            gate_passed INTEGER,
            gate_reasons_json TEXT,
            snapshot_json TEXT NOT NULL,
            prompt TEXT NOT NULL,
            raw_response TEXT NOT NULL,
            decision_json TEXT NOT NULL,
            suggested_order_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            status TEXT NOT NULL,
            entry_type TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            quantity REAL,
            notional_usdt REAL,
            margin_usdt REAL,
            leverage REAL,
            risk_usdt REAL,
            reward_risk REAL,
            notes TEXT,
            FOREIGN KEY(decision_id) REFERENCES ai_decisions(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_decisions_created_at ON ai_decisions(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_status ON paper_trades(status)")
    conn.commit()
    return conn


def save_result(
    conn: sqlite3.Connection,
    snapshot: dict[str, Any],
    prompt: str,
    raw_response: str,
    decision: dict[str, Any],
    gate: GateResult,
) -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO ai_decisions (
            created_at, symbol, latest_price, decision, confidence, gate_passed,
            gate_reasons_json, snapshot_json, prompt, raw_response, decision_json, suggested_order_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            created_at,
            snapshot["symbol"],
            snapshot["latest_price"],
            decision.get("decision"),
            decision.get("confidence"),
            1 if gate.passed else 0,
            json.dumps(gate.reasons, ensure_ascii=False),
            json.dumps(snapshot, ensure_ascii=False),
            prompt,
            raw_response,
            json.dumps(decision, ensure_ascii=False),
            json.dumps(gate.suggested_order, ensure_ascii=False) if gate.suggested_order else None,
        ),
    )
    decision_id = int(cursor.lastrowid)
    if gate.passed and gate.suggested_order:
        order = gate.suggested_order
        conn.execute(
            """
            INSERT INTO paper_trades (
                decision_id, created_at, symbol, side, status, entry_type, entry_price,
                stop_loss, take_profit, quantity, notional_usdt, margin_usdt, leverage,
                risk_usdt, reward_risk, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                created_at,
                order["symbol"],
                order["side"],
                "planned",
                order["entry_type"],
                order["entry"],
                order["stop_loss"],
                order["take_profit"],
                order["quantity"],
                order["notional_usdt"],
                order["margin_usdt"],
                order["leverage"],
                order["risk_usdt"],
                order["reward_risk"],
                "Paper-only plan. No real order was sent.",
            ),
        )
    conn.commit()
    return decision_id


def write_codex_packet(config_path: Path, output_path: Path) -> Path:
    config = load_config(config_path)
    config_dir = config_path.parent if config_path.exists() else Path.cwd()
    snapshot = build_snapshot(config, config_dir)
    prompt = build_prompt(snapshot, config)
    packet = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "codex_manual_decision",
        "instructions": [
            "Paste or show this packet to Codex.",
            "Codex should return one JSON decision object only.",
            "Save that JSON to a decision file, then run this tool with --decision-file.",
        ],
        "decision_schema": {
            "decision": "long | short | no_trade",
            "confidence": "integer 0-100",
            "entry_type": "market | limit | stop | none",
            "entry": "number or null",
            "stop_loss": "number or null",
            "take_profit": "number or null",
            "time_horizon": "intraday | 1-3d | swing | none",
            "reason": "short, data-based reason",
            "invalid_if": "condition that invalidates the idea",
            "key_risks": ["risk 1", "risk 2"],
        },
        "prompt": prompt,
        "snapshot": snapshot,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def run_once(
    config_path: Path,
    print_prompt: bool = False,
    decision_file: Path | None = None,
    prompt_out: Path | None = None,
) -> int:
    config = load_config(config_path)
    config_dir = config_path.parent if config_path.exists() else Path.cwd()
    snapshot = build_snapshot(config, config_dir)
    prompt = build_prompt(snapshot, config)
    if prompt_out:
        prompt_out.parent.mkdir(parents=True, exist_ok=True)
        prompt_out.write_text(prompt, encoding="utf-8")
    if print_prompt:
        print(prompt)
    if decision_file:
        raw_response = decision_file.read_text(encoding="utf-8")
        raw_decision = json.loads(raw_response)
    else:
        raw_decision, raw_response = call_ai(prompt, config)
    decision = normalize_decision(raw_decision)
    gate = risk_gate(decision, snapshot, config)
    db_path = resolve_path(config["database"], config_dir)
    with init_db(db_path) as conn:
        decision_id = save_result(conn, snapshot, prompt, raw_response, decision, gate)

    print("\nAI Daily Trader V1")
    print(f"decision_id: {decision_id}")
    print(f"symbol: {snapshot['symbol']}")
    print(f"latest_price: {snapshot['latest_price']}")
    print(f"market_regime: {snapshot['market_regime']}")
    print(f"ai_decision: {decision['decision']} confidence={decision['confidence']}")
    print(f"gate: {'PASS' if gate.passed else 'REJECT'}")
    if gate.reasons:
        print("gate_reasons:")
        for reason in gate.reasons:
            print(f"- {reason}")
    if gate.suggested_order:
        print("suggested_order:")
        print(json.dumps(gate.suggested_order, ensure_ascii=False, indent=2))
    print(f"database: {db_path}")
    return decision_id


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Daily Trader V1 - paper-only AI trading plan generator.")
    parser.add_argument("--config", default="user_data/ai_daily_trader_v1_config.json", help="Path to config JSON.")
    parser.add_argument("--once", action="store_true", help="Run once and exit.")
    parser.add_argument("--loop", action="store_true", help="Run forever using scan_interval_minutes.")
    parser.add_argument("--print-prompt", action="store_true", help="Print the full prompt sent to the model.")
    parser.add_argument("--prompt-out", help="Write the model prompt to a text file.")
    parser.add_argument("--prepare-codex", action="store_true", help="Write a Codex decision packet and exit without recording a decision.")
    parser.add_argument(
        "--codex-packet-out",
        default="user_data/ai_daily_trader_v1_codex_packet.json",
        help="Where to write the Codex decision packet.",
    )
    parser.add_argument("--decision-file", help="Use a local JSON decision file instead of calling an API.")
    args = parser.parse_args()

    config_path = Path(args.config)
    if args.prepare_codex:
        output_path = resolve_path(args.codex_packet_out, config_path.parent if config_path.exists() else Path.cwd())
        written = write_codex_packet(config_path, output_path)
        print(f"Codex packet written: {written}")
        return 0

    if args.loop:
        while True:
            config = load_config(config_path)
            try:
                run_once(
                    config_path,
                    print_prompt=args.print_prompt,
                    decision_file=Path(args.decision_file) if args.decision_file else None,
                    prompt_out=Path(args.prompt_out) if args.prompt_out else None,
                )
            except Exception as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
            time.sleep(int(config.get("scan_interval_minutes", 1440)) * 60)
    else:
        run_once(
            config_path,
            print_prompt=args.print_prompt,
            decision_file=Path(args.decision_file) if args.decision_file else None,
            prompt_out=Path(args.prompt_out) if args.prompt_out else None,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
