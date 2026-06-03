"""
Moonshot Watchlist V1

Scans local Freqtrade futures candles and creates a high-risk opportunity report.
This is a decision-support tool, not an auto-trading strategy.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "user_data" / "data" / "okx" / "futures"
REPORT_DIR = ROOT / "user_data" / "reports"
JSON_OUT = REPORT_DIR / "moonshot_watchlist_latest.json"
MD_OUT = REPORT_DIR / "moonshot_watchlist_latest.md"


CORE_PAIRS = {
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
    "PEPE/USDT:USDT",
    "WIF/USDT:USDT",
    "BONK/USDT:USDT",
    "FLOKI/USDT:USDT",
    "SUI/USDT:USDT",
    "BNB/USDT:USDT",
    "LINK/USDT:USDT",
    "AVAX/USDT:USDT",
    "NEAR/USDT:USDT",
    "ADA/USDT:USDT",
}


def pair_from_filename(path: Path) -> str:
    name = path.name.replace("-1h-futures.feather", "")
    sep = "_" if "_" in name else "-"
    base, quote, settle = name.split(sep)
    return f"{base}/{quote}:{settle}"


def pct(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value * 100:.2f}%"


def num(value: float | None, digits: int = 2) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.{digits}f}"


def safe_return(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods:
        return None
    old = float(close.iloc[-periods - 1])
    latest = float(close.iloc[-1])
    if old <= 0:
        return None
    return latest / old - 1.0


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - 100 / (1 + rs)


def analyze_pair(path: Path) -> dict[str, Any] | None:
    pair = pair_from_filename(path)
    df = pd.read_feather(path)
    if df.empty or len(df) < 220:
        return None

    df = df.sort_values("date").reset_index(drop=True)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    latest_close = float(close.iloc[-1])
    latest_time = pd.Timestamp(df["date"].iloc[-1]).to_pydatetime()
    if latest_time.tzinfo is None:
        latest_time = latest_time.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_hours = (now - latest_time.astimezone(timezone.utc)).total_seconds() / 3600

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    rsi = calc_rsi(close, 14)
    high_55 = high.rolling(55).max()
    low_55 = low.rolling(55).min()
    high_110 = high.rolling(110).max()
    low_110 = low.rolling(110).min()

    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean()
    atr_pct = float(atr.iloc[-1] / latest_close) if latest_close > 0 else None
    vol_ratio_24 = float(volume.iloc[-1] / volume.rolling(24).mean().iloc[-1])
    vol_ratio_72 = float(volume.iloc[-1] / volume.rolling(72).mean().iloc[-1])

    trend_strength = float((ema20.iloc[-1] / ema200.iloc[-1]) - 1.0)
    ret_24h = safe_return(close, 24)
    ret_7d = safe_return(close, 24 * 7)
    ret_30d = safe_return(close, 24 * 30)
    breakout_55 = float(latest_close / high_55.iloc[-1] - 1.0)
    breakdown_55 = float(latest_close / low_55.iloc[-1] - 1.0)
    high_position = float((latest_close - low_110.iloc[-1]) / (high_110.iloc[-1] - low_110.iloc[-1]))

    long_score = 0
    short_score = 0

    if latest_close > ema20.iloc[-1] > ema50.iloc[-1] > ema200.iloc[-1]:
        long_score += 3
    if latest_close < ema20.iloc[-1] < ema50.iloc[-1] < ema200.iloc[-1]:
        short_score += 3

    if ret_7d is not None and ret_7d > 0.12:
        long_score += 2
    if ret_7d is not None and ret_7d < -0.12:
        short_score += 2

    if breakout_55 > -0.01:
        long_score += 2
    if breakdown_55 < 0.01:
        short_score += 2

    if 0.55 <= float(rsi.iloc[-1]) / 100 <= 0.78:
        long_score += 1
    if 0.22 <= float(rsi.iloc[-1]) / 100 <= 0.45:
        short_score += 1

    if vol_ratio_24 > 1.3 or vol_ratio_72 > 1.4:
        long_score += 1
        short_score += 1

    if atr_pct is not None and 0.008 <= atr_pct <= 0.07:
        long_score += 1
        short_score += 1
    elif atr_pct is not None and atr_pct > 0.10:
        long_score -= 2
        short_score -= 2

    if high_position > 0.75:
        long_score += 1
    if high_position < 0.25:
        short_score += 1

    if age_hours > 48:
        long_score -= 3
        short_score -= 3

    if pair == "BTC/USDT:USDT":
        long_score -= 1
        short_score -= 1

    bias = "neutral"
    if long_score >= 7 and long_score >= short_score + 2:
        bias = "long_watch"
    elif short_score >= 7 and short_score >= long_score + 2:
        bias = "short_watch"

    return {
        "pair": pair,
        "is_core_pair": pair in CORE_PAIRS,
        "latest_time_utc": latest_time.astimezone(timezone.utc).isoformat(),
        "age_hours": round(age_hours, 2),
        "stale": age_hours > 48,
        "close": latest_close,
        "ret_24h": ret_24h,
        "ret_7d": ret_7d,
        "ret_30d": ret_30d,
        "ema20_vs_ema200": trend_strength,
        "rsi_14": float(rsi.iloc[-1]),
        "atr_pct": atr_pct,
        "volume_ratio_24h": vol_ratio_24,
        "volume_ratio_72h": vol_ratio_72,
        "breakout_55": breakout_55,
        "breakdown_55": breakdown_55,
        "high_position_110": high_position,
        "long_score": long_score,
        "short_score": short_score,
        "bias": bias,
    }


def render_markdown(rows: list[dict[str, Any]]) -> str:
    generated = datetime.now(timezone.utc).isoformat()
    long_rows = sorted(rows, key=lambda x: (x["long_score"], x["ret_7d"] or -999), reverse=True)
    short_rows = sorted(rows, key=lambda x: (x["short_score"], -(x["ret_7d"] or 999)), reverse=True)
    stale_count = sum(1 for row in rows if row["stale"])

    lines = [
        "# Moonshot Watchlist V1",
        "",
        f"- Generated UTC: {generated}",
        f"- Scanned pairs: {len(rows)}",
        f"- Stale data pairs older than 48h: {stale_count}",
        "",
        "This report is a high-risk opportunity radar. It is not a promise of profit and does not replace backtesting.",
        "",
        "## Long Momentum Candidates",
        "",
        "| Rank | Pair | Score | 24h | 7d | 30d | RSI | ATR% | Vol24 | Breakout55 | Data Age |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(long_rows[:15], 1):
        lines.append(
            "| {idx} | {pair} | {score} | {ret24} | {ret7} | {ret30} | {rsi} | {atr} | {vol} | {brk} | {age}h |".format(
                idx=idx,
                pair=row["pair"],
                score=row["long_score"],
                ret24=pct(row["ret_24h"]),
                ret7=pct(row["ret_7d"]),
                ret30=pct(row["ret_30d"]),
                rsi=num(row["rsi_14"], 1),
                atr=pct(row["atr_pct"]),
                vol=num(row["volume_ratio_24h"], 2),
                brk=pct(row["breakout_55"]),
                age=num(row["age_hours"], 1),
            )
        )

    lines.extend(
        [
            "",
            "## Short Breakdown Candidates",
            "",
            "| Rank | Pair | Score | 24h | 7d | 30d | RSI | ATR% | Vol24 | Breakdown55 | Data Age |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for idx, row in enumerate(short_rows[:15], 1):
        lines.append(
            "| {idx} | {pair} | {score} | {ret24} | {ret7} | {ret30} | {rsi} | {atr} | {vol} | {bd} | {age}h |".format(
                idx=idx,
                pair=row["pair"],
                score=row["short_score"],
                ret24=pct(row["ret_24h"]),
                ret7=pct(row["ret_7d"]),
                ret30=pct(row["ret_30d"]),
                rsi=num(row["rsi_14"], 1),
                atr=pct(row["atr_pct"]),
                vol=num(row["volume_ratio_24h"], 2),
                bd=pct(row["breakdown_55"]),
                age=num(row["age_hours"], 1),
            )
        )

    lines.extend(
        [
            "",
            "## How To Read",
            "",
            "- Long score means the coin is close to a high-volatility upside breakout.",
            "- Short score means the coin is close to a weak-trend downside breakdown.",
            "- Stale data must be refreshed before acting.",
            "- The best use is to decide which pairs deserve deeper strategy backtesting or manual review.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(DATA_DIR.glob("*-1h-futures.feather"))
    rows = []
    for path in paths:
        try:
            item = analyze_pair(path)
        except Exception as exc:
            print(f"skip {path.name}: {exc}")
            continue
        if item is not None:
            rows.append(item)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(DATA_DIR),
        "rows": rows,
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(rows), encoding="utf-8")
    print(f"wrote {JSON_OUT}")
    print(f"wrote {MD_OUT}")


if __name__ == "__main__":
    main()
