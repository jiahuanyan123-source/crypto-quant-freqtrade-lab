import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline


DEFAULT_PAIRS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
    "BCH/USDT:USDT",
]

FEATURE_COLUMNS = [
    "rsi",
    "adx",
    "atr_pct",
    "roc_3",
    "roc_12",
    "roc_36",
    "ema_spread",
    "bb_width",
    "bb_width_median",
    "volume_ratio",
    "range_pct",
    "body_pct",
    "upper_wick_pct",
    "lower_wick_pct",
    "rsi_1h",
    "adx_1h",
    "atr_pct_1h",
    "roc_6_1h",
    "roc_24_1h",
    "roc_72_1h",
    "roc_168_1h",
    "roc_720_1h",
    "roc_1440_1h",
    "ema20_distance_1h",
    "ema200_distance_1h",
    "dd_60d_1h",
    "rebound_30d_1h",
    "btc_rsi_1h",
    "btc_adx_1h",
    "btc_atr_pct_1h",
    "btc_roc_6_1h",
    "btc_roc_24_1h",
    "btc_roc_72_1h",
    "btc_roc_168_1h",
    "btc_roc_720_1h",
    "btc_roc_1440_1h",
    "btc_ema20_distance_1h",
    "btc_ema200_distance_1h",
    "btc_dd_60d_1h",
    "btc_rebound_30d_1h",
    "relative_roc_24_1h",
    "relative_roc_168_1h",
    "v5_btc_bull_score",
    "v5_btc_bear_score",
    "v5_pair_long_score",
    "v5_pair_short_score",
    "v5_market_edge",
    "v5_bull_regime",
    "v5_hot_bull_regime",
    "v5_bear_regime",
    "v5_chop_regime",
    "v5_risk_off",
    "v5_trade_allowed",
    "trend_up",
    "trend_down",
    "controlled_volatility",
    "range_regime",
]


def pair_to_file_stem(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def atr(dataframe: pd.DataFrame, period: int = 14) -> pd.Series:
    high = dataframe["high"]
    low = dataframe["low"]
    close = dataframe["close"]
    true_range = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False).mean()


def adx(dataframe: pd.DataFrame, period: int = 14) -> pd.Series:
    high = dataframe["high"]
    low = dataframe["low"]
    close = dataframe["close"]

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_value = true_range.ewm(alpha=1.0 / period, adjust=False).mean()
    plus_di = 100.0 * pd.Series(plus_dm, index=dataframe.index).ewm(alpha=1.0 / period, adjust=False).mean() / atr_value
    minus_di = 100.0 * pd.Series(minus_dm, index=dataframe.index).ewm(alpha=1.0 / period, adjust=False).mean() / atr_value
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1.0 / period, adjust=False).mean()


def add_fast_indicators(dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = dataframe.copy()
    dataframe["ema_12"] = dataframe["close"].ewm(span=12, adjust=False).mean()
    dataframe["ema_36"] = dataframe["close"].ewm(span=36, adjust=False).mean()
    dataframe["ema_96"] = dataframe["close"].ewm(span=96, adjust=False).mean()
    dataframe["rsi"] = rsi(dataframe["close"], 14)
    dataframe["adx"] = adx(dataframe, 14)
    dataframe["atr"] = atr(dataframe, 14)
    dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
    dataframe["roc_3"] = dataframe["close"].pct_change(3)
    dataframe["roc_12"] = dataframe["close"].pct_change(12)
    dataframe["roc_36"] = dataframe["close"].pct_change(36)
    dataframe["ema_spread"] = (dataframe["ema_12"] - dataframe["ema_96"]).abs() / dataframe["close"]

    dataframe["bb_mid"] = dataframe["close"].rolling(20).mean()
    bb_std = dataframe["close"].rolling(20).std()
    dataframe["bb_width"] = (4.0 * bb_std) / dataframe["bb_mid"]
    dataframe["bb_width_median"] = dataframe["bb_width"].rolling(288).median()

    dataframe["volume_mean_48"] = dataframe["volume"].rolling(48).mean()
    dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean_48"]
    dataframe["high_48"] = dataframe["high"].rolling(48).max().shift(1)
    dataframe["low_48"] = dataframe["low"].rolling(48).min().shift(1)
    dataframe["high_144"] = dataframe["high"].rolling(144).max().shift(1)
    dataframe["low_144"] = dataframe["low"].rolling(144).min().shift(1)
    dataframe["range_pct"] = (dataframe["high"] - dataframe["low"]) / dataframe["close"]
    dataframe["body_pct"] = (dataframe["close"] - dataframe["open"]).abs() / dataframe["close"]
    dataframe["upper_wick_pct"] = dataframe["high"] - dataframe[["open", "close"]].max(axis=1)
    dataframe["upper_wick_pct"] = dataframe["upper_wick_pct"] / dataframe["close"]
    dataframe["lower_wick_pct"] = dataframe[["open", "close"]].min(axis=1) - dataframe["low"]
    dataframe["lower_wick_pct"] = dataframe["lower_wick_pct"] / dataframe["close"]
    dataframe["atr_pct_mean_288"] = dataframe["atr_pct"].rolling(288).mean()

    dataframe["trend_up"] = (
        (dataframe["close"] > dataframe["ema_36"])
        & (dataframe["ema_12"] > dataframe["ema_36"])
        & (dataframe["ema_36"] > dataframe["ema_96"])
    )
    dataframe["trend_down"] = (
        (dataframe["close"] < dataframe["ema_36"])
        & (dataframe["ema_12"] < dataframe["ema_36"])
        & (dataframe["ema_36"] < dataframe["ema_96"])
    )
    dataframe["range_regime"] = (
        (dataframe["adx"] < 14)
        & (dataframe["bb_width"] < dataframe["bb_width_median"] * 0.82)
        & (dataframe["atr_pct"] < 0.003)
    )
    dataframe["controlled_volatility"] = (
        (dataframe["atr_pct"] > 0.0014)
        & (dataframe["atr_pct"] < 0.026)
        & (dataframe["range_pct"] < 0.046)
        & (dataframe["atr_pct"] < dataframe["atr_pct_mean_288"] * 2.25)
        & (dataframe["volume_ratio"] < 8.0)
    )
    return dataframe


def add_hourly_indicators(dataframe: pd.DataFrame, prefix: str = "") -> pd.DataFrame:
    dataframe = dataframe.copy()
    dataframe[f"{prefix}ema_20"] = dataframe["close"].ewm(span=20, adjust=False).mean()
    dataframe[f"{prefix}ema_50"] = dataframe["close"].ewm(span=50, adjust=False).mean()
    dataframe[f"{prefix}ema_200"] = dataframe["close"].ewm(span=200, adjust=False).mean()
    dataframe[f"{prefix}rsi"] = rsi(dataframe["close"], 14)
    dataframe[f"{prefix}adx"] = adx(dataframe, 14)
    dataframe[f"{prefix}atr"] = atr(dataframe, 14)
    dataframe[f"{prefix}atr_pct"] = dataframe[f"{prefix}atr"] / dataframe["close"]
    dataframe[f"{prefix}roc_6"] = dataframe["close"].pct_change(6)
    dataframe[f"{prefix}roc_24"] = dataframe["close"].pct_change(24)
    dataframe[f"{prefix}roc_72"] = dataframe["close"].pct_change(72)
    dataframe[f"{prefix}roc_168"] = dataframe["close"].pct_change(168)
    dataframe[f"{prefix}roc_720"] = dataframe["close"].pct_change(720)
    dataframe[f"{prefix}roc_1440"] = dataframe["close"].pct_change(1440)
    dataframe[f"{prefix}high_24"] = dataframe["high"].rolling(24).max().shift(1)
    dataframe[f"{prefix}low_24"] = dataframe["low"].rolling(24).min().shift(1)
    dataframe[f"{prefix}high_168"] = dataframe["high"].rolling(168).max().shift(1)
    dataframe[f"{prefix}low_168"] = dataframe["low"].rolling(168).min().shift(1)
    dataframe[f"{prefix}high_720"] = dataframe["high"].rolling(720).max().shift(1)
    dataframe[f"{prefix}low_720"] = dataframe["low"].rolling(720).min().shift(1)
    dataframe[f"{prefix}high_1440"] = dataframe["high"].rolling(1440).max().shift(1)
    dataframe[f"{prefix}low_1440"] = dataframe["low"].rolling(1440).min().shift(1)
    dataframe[f"{prefix}ema20_distance"] = (dataframe["close"] - dataframe[f"{prefix}ema_20"]) / dataframe["close"]
    dataframe[f"{prefix}ema200_distance"] = (dataframe["close"] - dataframe[f"{prefix}ema_200"]) / dataframe["close"]
    dataframe[f"{prefix}dd_60d"] = dataframe["close"] / dataframe[f"{prefix}high_1440"] - 1.0
    dataframe[f"{prefix}rebound_30d"] = dataframe["close"] / dataframe[f"{prefix}low_720"] - 1.0
    dataframe[f"{prefix}atr_pct_median_30d"] = dataframe[f"{prefix}atr_pct"].rolling(720).median()
    dataframe[f"{prefix}atr_pct_median_60d"] = dataframe[f"{prefix}atr_pct"].rolling(1440).median()
    return dataframe


def suffix_hourly(dataframe: pd.DataFrame) -> pd.DataFrame:
    columns = {column: f"{column}_1h" for column in dataframe.columns if column != "date"}
    return dataframe.rename(columns=columns)


def load_ohlcv(data_dir: Path, pair: str, timeframe: str) -> pd.DataFrame:
    path = data_dir / f"{pair_to_file_stem(pair)}-{timeframe}-futures.feather"
    if not path.exists():
        raise FileNotFoundError(path)
    dataframe = pd.read_feather(path).sort_values("date").reset_index(drop=True)
    dataframe["date"] = pd.to_datetime(dataframe["date"], utc=True)
    return dataframe


def future_extremes(dataframe: pd.DataFrame, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    high = dataframe["high"].to_numpy(dtype=float)
    low = dataframe["low"].to_numpy(dtype=float)
    future_high = np.full(len(dataframe), np.nan)
    future_low = np.full(len(dataframe), np.nan)
    if len(dataframe) <= horizon:
        return future_high, future_low

    high_windows = np.lib.stride_tricks.sliding_window_view(high[1:], horizon)
    low_windows = np.lib.stride_tricks.sliding_window_view(low[1:], horizon)
    future_high[: len(high_windows)] = high_windows.max(axis=1)
    future_low[: len(low_windows)] = low_windows.min(axis=1)
    return future_high, future_low


def build_pair_frame(
    data_dir: Path,
    pair: str,
    btc_1h: pd.DataFrame,
    start_date: pd.Timestamp,
    warmup_start: pd.Timestamp,
    end_date: pd.Timestamp,
    horizon: int,
    take_profit: float,
    stop_loss: float,
) -> pd.DataFrame:
    base = load_ohlcv(data_dir, pair, "5m")
    pair_1h = load_ohlcv(data_dir, pair, "1h")

    base = base[(base["date"] >= warmup_start) & (base["date"] <= end_date)].copy()
    pair_1h = pair_1h[(pair_1h["date"] >= warmup_start - pd.Timedelta(days=70)) & (pair_1h["date"] <= end_date)].copy()

    base = add_fast_indicators(base)
    pair_1h = suffix_hourly(add_hourly_indicators(pair_1h))

    merged = pd.merge_asof(base.sort_values("date"), pair_1h.sort_values("date"), on="date", direction="backward")
    merged = pd.merge_asof(merged.sort_values("date"), btc_1h.sort_values("date"), on="date", direction="backward")

    merged["relative_roc_24_1h"] = merged["roc_24_1h"] - merged["btc_roc_24_1h"]
    merged["relative_roc_168_1h"] = merged["roc_168_1h"] - merged["btc_roc_168_1h"]
    merged["v5_btc_bull_score"] = (
        (merged["btc_close_1h"] > merged["btc_ema_20_1h"]).astype(int)
        + (merged["btc_ema_20_1h"] > merged["btc_ema_50_1h"]).astype(int)
        + (merged["btc_ema_50_1h"] > merged["btc_ema_200_1h"]).astype(int)
        + (merged["btc_close_1h"] > merged["btc_ema_200_1h"]).astype(int)
        + (merged["btc_rsi_1h"] > 52).astype(int)
        + (merged["btc_adx_1h"] > 17).astype(int)
        + (merged["btc_roc_168_1h"] > 0.02).astype(int)
        + (merged["btc_roc_720_1h"] > 0.06).astype(int)
        + (merged["btc_dd_60d_1h"] > -0.24).astype(int)
    )
    merged["v5_btc_bear_score"] = (
        (merged["btc_close_1h"] < merged["btc_ema_20_1h"]).astype(int)
        + (merged["btc_ema_20_1h"] < merged["btc_ema_50_1h"]).astype(int)
        + (merged["btc_ema_50_1h"] < merged["btc_ema_200_1h"]).astype(int)
        + (merged["btc_close_1h"] < merged["btc_ema_200_1h"]).astype(int)
        + (merged["btc_rsi_1h"] < 48).astype(int)
        + (merged["btc_adx_1h"] > 17).astype(int)
        + (merged["btc_roc_168_1h"] < -0.02).astype(int)
        + (merged["btc_roc_720_1h"] < -0.06).astype(int)
        + (merged["btc_dd_60d_1h"] < -0.18).astype(int)
    )
    merged["v5_pair_long_score"] = (
        (merged["close_1h"] > merged["ema_20_1h"]).astype(int)
        + (merged["ema_20_1h"] > merged["ema_50_1h"]).astype(int)
        + (merged["close_1h"] > merged["ema_200_1h"]).astype(int)
        + (merged["rsi_1h"] > 52).astype(int)
        + (merged["adx_1h"] > 17).astype(int)
        + (merged["roc_24_1h"] > 0.01).astype(int)
        + (merged["roc_168_1h"] > 0.03).astype(int)
        + (merged["relative_roc_168_1h"] > -0.02).astype(int)
    )
    merged["v5_pair_short_score"] = (
        (merged["close_1h"] < merged["ema_20_1h"]).astype(int)
        + (merged["ema_20_1h"] < merged["ema_50_1h"]).astype(int)
        + (merged["close_1h"] < merged["ema_200_1h"]).astype(int)
        + (merged["rsi_1h"] < 48).astype(int)
        + (merged["adx_1h"] > 17).astype(int)
        + (merged["roc_24_1h"] < -0.01).astype(int)
        + (merged["roc_168_1h"] < -0.03).astype(int)
        + (merged["relative_roc_168_1h"] < 0.02).astype(int)
    )
    merged["v5_market_edge"] = merged["v5_btc_bull_score"] - merged["v5_btc_bear_score"]
    merged["v5_bull_regime"] = (
        (merged["v5_btc_bull_score"] >= 6)
        & (merged["v5_market_edge"] >= 3)
        & (merged["btc_roc_720_1h"] > 0.035)
        & (merged["btc_dd_60d_1h"] > -0.24)
        & (merged["btc_atr_pct_1h"] < merged["btc_atr_pct_median_60d_1h"] * 2.35)
    )
    merged["v5_hot_bull_regime"] = (
        merged["v5_bull_regime"]
        & (merged["v5_btc_bull_score"] >= 7)
        & (merged["btc_roc_168_1h"] > 0.06)
        & (merged["btc_roc_720_1h"] > 0.12)
        & (merged["btc_close_1h"] > merged["btc_high_168_1h"] * 0.98)
    )
    merged["v5_bear_regime"] = (
        (merged["v5_btc_bear_score"] >= 6)
        & (merged["v5_market_edge"] <= -3)
        & (merged["btc_roc_720_1h"] < -0.035)
        & (merged["btc_close_1h"] < merged["btc_ema_50_1h"])
        & (merged["btc_atr_pct_1h"] < merged["btc_atr_pct_median_60d_1h"] * 2.50)
    )
    merged["v5_chop_regime"] = (
        (merged["v5_market_edge"].abs() <= 2)
        & (merged["btc_adx_1h"] < 18)
        & (merged["btc_roc_720_1h"].abs() < 0.08)
    )
    merged["v5_risk_off"] = (
        (merged["btc_roc_24_1h"] < -0.075)
        | (merged["btc_roc_168_1h"] < -0.16)
        | (merged["btc_dd_60d_1h"] < -0.34)
        | (merged["btc_atr_pct_1h"] > merged["btc_atr_pct_median_60d_1h"] * 2.80)
    )
    merged["v5_trade_allowed"] = ~merged["v5_chop_regime"] & ~merged["v5_risk_off"]

    future_high, future_low = future_extremes(merged, horizon)
    close = merged["close"].to_numpy(dtype=float)
    long_reward = future_high / close - 1.0
    long_risk = 1.0 - future_low / close
    short_reward = 1.0 - future_low / close
    short_risk = future_high / close - 1.0

    merged["long_y"] = ((long_reward >= take_profit) & ((long_reward / take_profit) >= (long_risk / stop_loss))).astype(int)
    merged["short_y"] = ((short_reward >= take_profit) & ((short_reward / take_profit) >= (short_risk / stop_loss))).astype(int)
    merged["pair"] = pair
    merged = merged[(merged["date"] >= start_date) & (merged["date"] <= end_date)]
    merged = merged[(merged["volume"] > 0) & merged["atr_pct"].notna() & merged["volume_ratio"].notna()]
    return merged


def choose_threshold(y_true: np.ndarray, probability: np.ndarray) -> tuple[float, dict]:
    best_threshold = 0.54
    best_score = -1.0
    best_metrics = {}
    base_rate = float(np.mean(y_true))

    for threshold in np.arange(0.50, 0.701, 0.01):
        selected = probability >= threshold
        selected_count = int(selected.sum())
        if selected_count < max(100, int(len(y_true) * 0.004)):
            continue
        precision = float(np.mean(y_true[selected])) if selected_count else 0.0
        recall = recall_score(y_true, selected, zero_division=0)
        coverage = selected_count / len(y_true)
        score = precision * np.sqrt(max(coverage, 1e-9))
        if precision < base_rate + 0.015:
            score *= 0.70
        if score > best_score:
            best_score = score
            best_threshold = float(threshold)
            best_metrics = {
                "base_rate": base_rate,
                "threshold": float(threshold),
                "precision": precision,
                "recall": float(recall),
                "coverage": float(coverage),
                "selected_count": selected_count,
            }

    return max(0.52, min(best_threshold, 0.68)), best_metrics


def model_pipeline(random_state: int) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=0.045,
                    max_iter=180,
                    max_leaf_nodes=24,
                    min_samples_leaf=45,
                    l2_regularization=0.20,
                    validation_fraction=0.15,
                    n_iter_no_change=12,
                    class_weight="balanced",
                    random_state=random_state,
                ),
            ),
        ]
    )


def train_side(dataset: pd.DataFrame, target: str, random_state: int) -> tuple[Pipeline, float, dict]:
    dataset = dataset.sort_values("date").reset_index(drop=True)
    split_index = int(len(dataset) * 0.76)
    train = dataset.iloc[:split_index]
    valid = dataset.iloc[split_index:]

    x_train = train[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    y_train = train[target].astype(int).to_numpy()
    x_valid = valid[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    y_valid = valid[target].astype(int).to_numpy()

    end_date = dataset["date"].max()
    age_days = (end_date - train["date"]).dt.total_seconds().to_numpy() / 86400.0
    sample_weight = 0.35 + np.exp(-age_days / 90.0)

    model = model_pipeline(random_state)
    model.fit(x_train, y_train, model__sample_weight=sample_weight)

    valid_probability = model.predict_proba(x_valid)[:, 1]
    threshold, threshold_metrics = choose_threshold(y_valid, valid_probability)
    selected = valid_probability >= threshold
    auc = roc_auc_score(y_valid, valid_probability) if len(np.unique(y_valid)) == 2 else 0.5

    metrics = {
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "train_positive_rate": float(np.mean(y_train)),
        "valid_positive_rate": float(np.mean(y_valid)),
        "auc": float(auc),
        "threshold_metrics": threshold_metrics,
        "precision_at_threshold": precision_score(y_valid, selected, zero_division=0),
        "recall_at_threshold": recall_score(y_valid, selected, zero_division=0),
    }
    return model, threshold, metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-data-dir", default="/freqtrade/user_data")
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--horizon-candles", type=int, default=288)
    parser.add_argument("--take-profit", type=float, default=0.040)
    parser.add_argument("--stop-loss", type=float, default=0.012)
    parser.add_argument("--max-rows-per-pair", type=int, default=22000)
    parser.add_argument("--end-date", default="")
    parser.add_argument("--pairs", nargs="*", default=DEFAULT_PAIRS)
    parser.add_argument("--output-name", default="moonshot_v6_ml_filter.joblib")
    args = parser.parse_args()

    user_data_dir = Path(args.user_data_dir)
    data_dir = user_data_dir / "data" / "okx" / "futures"
    output_dir = user_data_dir / "ml_models"
    output_dir.mkdir(parents=True, exist_ok=True)

    btc_1h_raw = load_ohlcv(data_dir, "BTC/USDT:USDT", "1h")
    if args.end_date:
        end_date = pd.Timestamp(args.end_date)
        if end_date.tzinfo is None:
            end_date = end_date.tz_localize("UTC")
        else:
            end_date = end_date.tz_convert("UTC")
    else:
        end_date = btc_1h_raw["date"].max().floor("D")
    start_date = end_date - pd.Timedelta(days=args.train_days)
    warmup_start = start_date - pd.Timedelta(days=75)

    btc_1h = btc_1h_raw[(btc_1h_raw["date"] >= warmup_start) & (btc_1h_raw["date"] <= end_date)].copy()
    btc_1h = add_hourly_indicators(btc_1h, prefix="btc_")
    btc_1h["btc_close"] = btc_1h["close"]
    btc_1h = suffix_hourly(
        btc_1h[
            [
                "date",
                "btc_close",
                "btc_ema_20",
                "btc_ema_50",
                "btc_ema_200",
                "btc_rsi",
                "btc_adx",
                "btc_atr_pct",
                "btc_roc_6",
                "btc_roc_24",
                "btc_roc_72",
                "btc_roc_168",
                "btc_roc_720",
                "btc_roc_1440",
                "btc_high_24",
                "btc_low_24",
                "btc_high_168",
                "btc_low_168",
                "btc_high_720",
                "btc_low_720",
                "btc_high_1440",
                "btc_low_1440",
                "btc_ema20_distance",
                "btc_ema200_distance",
                "btc_dd_60d",
                "btc_rebound_30d",
                "btc_atr_pct_median_30d",
                "btc_atr_pct_median_60d",
            ]
        ]
    )

    frames = []
    pair_summaries = []
    for pair in args.pairs:
        try:
            frame = build_pair_frame(
                data_dir=data_dir,
                pair=pair,
                btc_1h=btc_1h,
                start_date=start_date,
                warmup_start=warmup_start,
                end_date=end_date,
                horizon=args.horizon_candles,
                take_profit=args.take_profit,
                stop_loss=args.stop_loss,
            )
            if len(frame) > args.max_rows_per_pair:
                age_days = (end_date - frame["date"]).dt.total_seconds() / 86400.0
                weights = (0.25 + np.exp(-age_days / 90.0)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
                if int((weights > 0).sum()) >= args.max_rows_per_pair:
                    try:
                        frame = frame.sample(args.max_rows_per_pair, random_state=42, weights=weights)
                    except ValueError:
                        frame = frame.sample(args.max_rows_per_pair, random_state=42)
                else:
                    frame = frame.sample(args.max_rows_per_pair, random_state=42)
            frames.append(frame)
            pair_summaries.append(
                {
                    "pair": pair,
                    "rows": int(len(frame)),
                    "long_positive_rate": float(frame["long_y"].mean()),
                    "short_positive_rate": float(frame["short_y"].mean()),
                }
            )
            print(f"{pair}: rows={len(frame)} long_pos={frame['long_y'].mean():.3f} short_pos={frame['short_y'].mean():.3f}")
        except Exception as exc:
            print(f"{pair}: skipped: {exc}")

    if not frames:
        raise RuntimeError("No training data was built.")

    dataset = pd.concat(frames, ignore_index=True)
    dataset = dataset.dropna(subset=["long_y", "short_y"])
    dataset = dataset.replace([np.inf, -np.inf], np.nan)
    dataset = dataset.dropna(subset=["date"])

    long_model, long_threshold, long_metrics = train_side(dataset, "long_y", random_state=42)
    short_model, short_threshold, short_metrics = train_side(dataset, "short_y", random_state=43)

    bundle = {
        "version": 1,
        "model_family": "sklearn_hist_gradient_boosting",
        "feature_columns": FEATURE_COLUMNS,
        "long_model": long_model,
        "short_model": short_model,
        "long_threshold": long_threshold,
        "short_threshold": short_threshold,
        "train_start": str(start_date),
        "train_end": str(end_date),
        "horizon_candles": args.horizon_candles,
        "take_profit": args.take_profit,
        "stop_loss": args.stop_loss,
        "pairs": args.pairs,
        "pair_summaries": pair_summaries,
        "long_metrics": long_metrics,
        "short_metrics": short_metrics,
    }

    model_path = output_dir / args.output_name
    meta_path = output_dir / args.output_name.replace(".joblib", ".json")
    joblib.dump(bundle, model_path)

    meta = {key: value for key, value in bundle.items() if key not in {"long_model", "short_model"}}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"saved_model={model_path}")
    print(f"saved_meta={meta_path}")
    print(f"long_threshold={long_threshold:.3f} auc={long_metrics['auc']:.3f}")
    print(f"short_threshold={short_threshold:.3f} auc={short_metrics['auc']:.3f}")


if __name__ == "__main__":
    main()
