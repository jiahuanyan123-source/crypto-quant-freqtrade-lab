from datetime import datetime, timezone
from typing import Optional

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair


class MultiAssetRegimeTrend4hV1(IStrategy):
    """
    Multi-asset 4h trend selection strategy.

    Hypothesis:
    - V4's strongest idea is not "ETH only"; it is "only trade liquid coins
      during confirmed 4h risk-on regimes".
    - Instead of forcing ETH shorts, rotate into liquid assets that show stronger
      4h trend continuation while BTC is not in a major bear/panic regime.
    """

    INTERFACE_VERSION = 3

    can_short = False
    timeframe = "4h"
    startup_candle_count = 600
    process_only_new_candles = True

    minimal_roi = {"0": 10.0}
    stoploss = -0.32

    trailing_stop = False
    use_custom_stoploss = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    position_adjustment_enable = False

    defensive_stake_fraction = 0.08
    base_stake_fraction = 0.14
    strong_stake_fraction = 0.22
    max_stake_fraction = 0.28

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": True,
        "stoploss_on_exchange_interval": 60,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    @property
    def protections(self) -> list[dict]:
        return [
            {
                "method": "CooldownPeriod",
                "stop_duration_candles": 2,
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 6 * 45,
                "trade_limit": 2,
                "stop_duration_candles": 6 * 10,
                "only_per_pair": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 6 * 180,
                "trade_limit": 6,
                "stop_duration_candles": 6 * 21,
                "max_allowed_drawdown": 0.28,
            },
        ]

    def informative_pairs(self) -> list[tuple[str, str]]:
        return [("BTC/USDT:USDT", "4h")]

    @staticmethod
    def _add_indicators(dataframe: DataFrame, prefix: str = "") -> DataFrame:
        dataframe[f"{prefix}ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe[f"{prefix}ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe[f"{prefix}ema_100"] = ta.EMA(dataframe, timeperiod=100)
        dataframe[f"{prefix}ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe[f"{prefix}rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe[f"{prefix}adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe[f"{prefix}atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe[f"{prefix}atr_pct"] = dataframe[f"{prefix}atr"] / dataframe["close"]
        dataframe[f"{prefix}atr_pct_median_90d"] = dataframe[f"{prefix}atr_pct"].rolling(6 * 90).median()
        dataframe[f"{prefix}roc_12"] = ta.ROC(dataframe, timeperiod=12) / 100.0
        dataframe[f"{prefix}roc_42"] = ta.ROC(dataframe, timeperiod=42) / 100.0
        dataframe[f"{prefix}roc_84"] = ta.ROC(dataframe, timeperiod=84) / 100.0
        dataframe[f"{prefix}roc_126"] = ta.ROC(dataframe, timeperiod=126) / 100.0
        dataframe[f"{prefix}roc_180"] = ta.ROC(dataframe, timeperiod=180) / 100.0
        dataframe[f"{prefix}volume_mean_30"] = dataframe["volume"].rolling(30).mean()
        dataframe[f"{prefix}volume_ratio"] = dataframe["volume"] / dataframe[f"{prefix}volume_mean_30"]
        dataframe[f"{prefix}high_80"] = dataframe["high"].rolling(80).max().shift(1)
        dataframe[f"{prefix}high_120"] = dataframe["high"].rolling(120).max().shift(1)
        dataframe[f"{prefix}low_55"] = dataframe["low"].rolling(55).min().shift(1)
        dataframe[f"{prefix}range_pct"] = (dataframe["high"] - dataframe["low"]) / dataframe["close"]
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self._add_indicators(dataframe)

        if self.dp:
            btc = self.dp.get_pair_dataframe(pair="BTC/USDT:USDT", timeframe="4h")
            btc = self._add_indicators(btc, prefix="btc_")
            btc["btc_close"] = btc["close"]
            btc = btc[
                [
                    "date",
                    "btc_close",
                    "btc_ema_20",
                    "btc_ema_50",
                    "btc_ema_100",
                    "btc_ema_200",
                    "btc_rsi",
                    "btc_adx",
                    "btc_atr_pct",
                    "btc_atr_pct_median_90d",
                    "btc_roc_12",
                    "btc_roc_42",
                    "btc_roc_84",
                    "btc_roc_126",
                    "btc_roc_180",
                ]
            ]
            dataframe = merge_informative_pair(dataframe, btc, self.timeframe, "4h", ffill=True)

        dataframe["btc_risk_on"] = (
            (dataframe["btc_close_4h"] > dataframe["btc_ema_100_4h"])
            & (dataframe["btc_ema_20_4h"] > dataframe["btc_ema_50_4h"])
            & (dataframe["btc_roc_84_4h"] > 0.015)
        ) | (
            (dataframe["btc_close_4h"] > dataframe["btc_ema_200_4h"])
            & (dataframe["btc_ema_50_4h"] > dataframe["btc_ema_200_4h"])
            & (dataframe["btc_roc_126_4h"] > 0)
        )
        dataframe["btc_panic"] = (
            (dataframe["btc_roc_42_4h"] < -0.120)
            & (dataframe["btc_rsi_4h"] < 36)
        )
        dataframe["asset_bull_regime"] = (
            (dataframe["close"] > dataframe["ema_100"])
            & (dataframe["ema_20"] > dataframe["ema_50"])
            & (dataframe["ema_50"] > dataframe["ema_100"])
            & (dataframe["roc_84"] > 0.040)
            & (dataframe["roc_126"] > 0.020)
        )
        dataframe["relative_strength"] = dataframe["roc_42"] - dataframe["btc_roc_42_4h"]
        dataframe["trend_quality"] = (
            dataframe["asset_bull_regime"].astype(int) * 4
            + dataframe["btc_risk_on"].astype(int) * 2
            + (dataframe["close"] > dataframe["ema_20"]).astype(int)
            + (dataframe["close"] > dataframe["ema_50"]).astype(int)
            + (dataframe["roc_42"] > 0.035).astype(int)
            + (dataframe["roc_84"] > 0.070).astype(int)
            + (dataframe["relative_strength"] > -0.010).astype(int)
            + (dataframe["volume_ratio"] > 0.80).astype(int)
            + (dataframe["adx"] > 16).astype(int)
        )
        dataframe["volatility_ok"] = (
            (dataframe["atr_pct"] > 0.006)
            & (dataframe["atr_pct"] < 0.105)
            & (dataframe["atr_pct"] < dataframe["atr_pct_median_90d"] * 2.10)
            & (dataframe["btc_atr_pct_4h"] < dataframe["btc_atr_pct_median_90d_4h"] * 2.00)
        )
        dataframe["overheated"] = (
            (dataframe["rsi"] > 79)
            | ((dataframe["roc_42"] > 0.330) & (dataframe["range_pct"] > dataframe["atr_pct_median_90d"] * 1.90))
        )
        dataframe["breakout_buffer_pct"] = (dataframe["atr_pct"] * 0.08).clip(lower=0.0015, upper=0.0070)
        dataframe["breakout_or_continuation"] = (
            dataframe["close"] > dataframe["high_80"] * (1.0 + dataframe["breakout_buffer_pct"])
        ) | (
            (dataframe["close"] > dataframe["ema_20"])
            & (dataframe["close"] > dataframe["high_120"] * 0.940)
            & (dataframe["roc_42"] > 0.055)
            & (dataframe["btc_roc_42_4h"] > -0.020)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["volume_ratio"] > 0.70)
            & dataframe["btc_risk_on"]
            & (~dataframe["btc_panic"])
            & dataframe["asset_bull_regime"]
            & dataframe["volatility_ok"]
            & (~dataframe["overheated"])
            & dataframe["breakout_or_continuation"]
            & (dataframe["rsi"].between(50, 76))
            & (dataframe["trend_quality"] >= 9)
        )

        dataframe.loc[long_entry, ["enter_long", "enter_tag"]] = (1, "multiasset_v1_4h_trend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_long = (
            (dataframe["close"] < dataframe["low_55"])
            | (
                (dataframe["close"] < dataframe["ema_100"])
                & (dataframe["roc_42"] < -0.030)
            )
            | (
                (dataframe["btc_close_4h"] < dataframe["btc_ema_200_4h"])
                & (dataframe["btc_roc_42_4h"] < 0)
            )
            | dataframe["btc_panic"]
        )

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = (1, "multiasset_v1_trend_exit")
        return dataframe

    def _last_analyzed_row(self, pair: str):
        if not self.dp:
            return None
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        return dataframe.iloc[-1]

    @staticmethod
    def _trade_hours(trade: Trade, current_time: datetime) -> float:
        opened = trade.open_date_utc
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        current = current_time
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return (current - opened).total_seconds() / 3600.0

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        last = self._last_analyzed_row(pair)
        if last is None:
            return None

        age_hours = self._trade_hours(trade, current_time)
        if age_hours >= 24 * 35 and current_profit < 0.08:
            return "multiasset_v1_stale_exit"

        try:
            max_profit = trade.calc_profit_ratio(trade.max_rate)
        except Exception:
            max_profit = current_profit

        if max_profit > 0.90 and current_profit < max_profit * 0.55:
            return "multiasset_v1_large_profit_retrace"
        if max_profit > 0.35 and current_profit < 0.06:
            return "multiasset_v1_breakeven_guard"

        if current_profit > 0.20 and float(last.get("close", current_rate)) < float(last.get("ema_50", current_rate)):
            return "multiasset_v1_trailing_exit"
        return None

    def _setup_quality(self, pair: str) -> tuple[float, float, float, bool]:
        last = self._last_analyzed_row(pair)
        if last is None:
            return 0.0, 0.03, 0.03, False

        quality = float(last.get("trend_quality", 0) or 0)
        atr_pct = float(last.get("atr_pct", 0.03) or 0.03)
        btc_atr_pct = float(last.get("btc_atr_pct_4h", 0.03) or 0.03)
        allowed = (
            bool(last.get("btc_risk_on", False))
            and bool(last.get("asset_bull_regime", False))
            and bool(last.get("volatility_ok", False))
            and not bool(last.get("btc_panic", False))
            and not bool(last.get("overheated", False))
        )
        if not allowed:
            quality -= 2.0
        return quality, atr_pct, btc_atr_pct, allowed

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: float,
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        quality, atr_pct, btc_atr_pct, allowed = self._setup_quality(pair)
        if not allowed:
            fraction = self.defensive_stake_fraction
        elif quality >= 12 and atr_pct < 0.045 and btc_atr_pct < 0.035:
            fraction = self.strong_stake_fraction
        elif quality >= 10 and atr_pct < 0.070:
            fraction = self.base_stake_fraction
        else:
            fraction = self.defensive_stake_fraction

        if atr_pct > 0.070 or btc_atr_pct > 0.050:
            fraction *= 0.70
        if atr_pct > 0.090:
            fraction *= 0.55

        risk_scale = float(self.config.get("multiasset4h_risk_scale", 1.0))
        fraction *= max(0.25, min(risk_scale, 1.35))

        stake = proposed_stake * max(0.05, min(fraction, self.max_stake_fraction))
        if min_stake:
            stake = max(stake, min_stake)
        return min(stake, max_stake)

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        try:
            runmode = getattr(self.config.get("runmode"), "value", "")
            if runmode not in {"live", "dry_run"}:
                return True
            orderbook = self.dp.orderbook(pair, 1)
            bid = float(orderbook["bids"][0][0])
            ask = float(orderbook["asks"][0][0])
            mid = (bid + ask) / 2.0
            spread = (ask - bid) / mid
            if spread > 0.0025:
                return False
            if rate > ask * 1.0025:
                return False
        except Exception:
            return True
        return True

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        configured_leverage = float(self.config.get("strategy_leverage", 4.0))
        leverage = min(configured_leverage, 4.0)
        try:
            quality, atr_pct, btc_atr_pct, allowed = self._setup_quality(pair)
            if not allowed:
                leverage = min(leverage, 1.5)
            elif quality >= 12 and atr_pct < 0.045 and btc_atr_pct < 0.035:
                leverage = min(leverage, 4.0)
            elif quality >= 10 and atr_pct < 0.070:
                leverage = min(leverage, 3.0)
            else:
                leverage = min(leverage, 2.0)
            if atr_pct > 0.070 or btc_atr_pct > 0.050:
                leverage = min(leverage, 2.0)
            if atr_pct > 0.090:
                leverage = min(leverage, 1.5)
        except Exception:
            leverage = min(configured_leverage, 1.5)
        return max(1.0, min(leverage, max_leverage))
