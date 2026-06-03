from datetime import datetime, timezone
from typing import Optional

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair


class MomentumSprint1hV1(IStrategy):
    """
    High-risk futures sprint strategy.

    Goal:
    - Use a small account slice to attack strong long/short momentum bursts.
    - Stay out of range noise.
    - Cut failed breakouts quickly and let rare winners expand.

    This is the offensive layer, not the steady compounding layer.
    Dry-run / research only. No strategy can guarantee profit.
    """

    INTERFACE_VERSION = 3

    can_short = True
    timeframe = "1h"
    startup_candle_count = 260
    process_only_new_candles = True

    minimal_roi = {"0": 10.0}
    stoploss = -0.30

    trailing_stop = False
    use_custom_stoploss = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    position_adjustment_enable = False

    base_stake_fraction = 0.12
    strong_stake_fraction = 0.20
    max_stake_fraction = 0.25

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
                "stop_duration_candles": 4,
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 72,
                "trade_limit": 2,
                "stop_duration_candles": 48,
                "only_per_pair": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 24 * 30,
                "trade_limit": 6,
                "stop_duration_candles": 24 * 7,
                "max_allowed_drawdown": 0.30,
            },
        ]

    def informative_pairs(self) -> list[tuple[str, str]]:
        return [
            ("BTC/USDT:USDT", "1h"),
            ("BTC/USDT:USDT", "4h"),
        ]

    @staticmethod
    def _add_indicators(dataframe: DataFrame, prefix: str = "") -> DataFrame:
        dataframe[f"{prefix}ema_12"] = ta.EMA(dataframe, timeperiod=12)
        dataframe[f"{prefix}ema_24"] = ta.EMA(dataframe, timeperiod=24)
        dataframe[f"{prefix}ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe[f"{prefix}ema_100"] = ta.EMA(dataframe, timeperiod=100)
        dataframe[f"{prefix}ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe[f"{prefix}rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe[f"{prefix}adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe[f"{prefix}atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe[f"{prefix}atr_pct"] = dataframe[f"{prefix}atr"] / dataframe["close"]
        dataframe[f"{prefix}roc_6"] = ta.ROC(dataframe, timeperiod=6) / 100.0
        dataframe[f"{prefix}roc_24"] = ta.ROC(dataframe, timeperiod=24) / 100.0
        dataframe[f"{prefix}roc_72"] = ta.ROC(dataframe, timeperiod=72) / 100.0
        dataframe[f"{prefix}roc_168"] = ta.ROC(dataframe, timeperiod=168) / 100.0
        dataframe[f"{prefix}volume_mean_24"] = dataframe["volume"].rolling(24).mean()
        dataframe[f"{prefix}volume_mean_72"] = dataframe["volume"].rolling(72).mean()
        dataframe[f"{prefix}volume_ratio_24"] = dataframe["volume"] / dataframe[f"{prefix}volume_mean_24"]
        dataframe[f"{prefix}volume_ratio_72"] = dataframe["volume"] / dataframe[f"{prefix}volume_mean_72"]
        dataframe[f"{prefix}high_24"] = dataframe["high"].rolling(24).max().shift(1)
        dataframe[f"{prefix}low_24"] = dataframe["low"].rolling(24).min().shift(1)
        dataframe[f"{prefix}high_55"] = dataframe["high"].rolling(55).max().shift(1)
        dataframe[f"{prefix}low_55"] = dataframe["low"].rolling(55).min().shift(1)
        dataframe[f"{prefix}high_110"] = dataframe["high"].rolling(110).max().shift(1)
        dataframe[f"{prefix}low_110"] = dataframe["low"].rolling(110).min().shift(1)
        dataframe[f"{prefix}range_pct"] = (dataframe["high"] - dataframe["low"]) / dataframe["close"]
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self._add_indicators(dataframe)

        if self.dp:
            btc_1h = self.dp.get_pair_dataframe(pair="BTC/USDT:USDT", timeframe="1h")
            btc_1h = self._add_indicators(btc_1h, prefix="btc_")
            btc_1h["btc_close"] = btc_1h["close"]
            btc_1h = btc_1h[
                [
                    "date",
                    "btc_close",
                    "btc_ema_24",
                    "btc_ema_50",
                    "btc_ema_100",
                    "btc_ema_200",
                    "btc_rsi",
                    "btc_adx",
                    "btc_atr_pct",
                    "btc_roc_6",
                    "btc_roc_24",
                    "btc_roc_72",
                    "btc_roc_168",
                ]
            ]
            dataframe = merge_informative_pair(dataframe, btc_1h, self.timeframe, "1h", ffill=True)

            btc_4h = self.dp.get_pair_dataframe(pair="BTC/USDT:USDT", timeframe="4h")
            btc_4h = self._add_indicators(btc_4h, prefix="btc4_")
            btc_4h["btc4_close"] = btc_4h["close"]
            btc_4h = btc_4h[
                [
                    "date",
                    "btc4_close",
                    "btc4_ema_50",
                    "btc4_ema_100",
                    "btc4_ema_200",
                    "btc4_rsi",
                    "btc4_atr_pct",
                    "btc4_roc_24",
                    "btc4_roc_72",
                    "btc4_roc_168",
                ]
            ]
            dataframe = merge_informative_pair(dataframe, btc_4h, self.timeframe, "4h", ffill=True)

        dataframe["breakout_buffer_pct"] = (dataframe["atr_pct"] * 0.08).clip(lower=0.0015, upper=0.0100)

        dataframe["target_bull_trend"] = (
            (dataframe["close"] > dataframe["ema_100"])
            & (dataframe["ema_12"] > dataframe["ema_24"])
            & (dataframe["ema_24"] > dataframe["ema_50"])
            & (dataframe["roc_24"] > 0.010)
            & (dataframe["roc_72"] > 0.020)
        )
        dataframe["target_bear_trend"] = (
            (dataframe["close"] < dataframe["ema_100"])
            & (dataframe["ema_12"] < dataframe["ema_24"])
            & (dataframe["ema_24"] < dataframe["ema_50"])
            & (dataframe["roc_24"] < -0.010)
            & (dataframe["roc_72"] < -0.020)
        )
        dataframe["btc_not_panic"] = ~(
            (dataframe["btc_roc_24_1h"] < -0.050)
            & (dataframe["btc_rsi_1h"] < 35)
        )
        dataframe["btc_not_euphoric"] = ~(
            (dataframe["btc_roc_24_1h"] > 0.055)
            & (dataframe["btc_rsi_1h"] > 72)
        )
        dataframe["btc_allows_long"] = (
            dataframe["btc_not_panic"]
            & (
                (dataframe["btc_close_1h"] > dataframe["btc_ema_100_1h"])
                | (dataframe["btc_roc_24_1h"] > -0.020)
                | (dataframe["btc4_close_4h"] > dataframe["btc4_ema_200_4h"])
            )
        )
        dataframe["btc_allows_short"] = (
            dataframe["btc_not_euphoric"]
            & (
                (dataframe["btc_close_1h"] < dataframe["btc_ema_100_1h"])
                | (dataframe["btc_roc_24_1h"] < 0.020)
                | (dataframe["btc4_close_4h"] < dataframe["btc4_ema_50_4h"])
            )
        )
        dataframe["volatility_ok"] = (
            (dataframe["atr_pct"] > 0.004)
            & (dataframe["atr_pct"] < 0.090)
            & (dataframe["range_pct"] < dataframe["atr_pct"] * 4.0)
        )
        dataframe["volume_ok"] = (
            (dataframe["volume"] > 0)
            & (dataframe["volume_ratio_24"] > 1.05)
            & (dataframe["volume_ratio_72"] > 0.85)
        )
        dataframe["relative_strength"] = dataframe["roc_24"] - dataframe["btc_roc_24_1h"]
        dataframe["relative_weakness"] = dataframe["btc_roc_24_1h"] - dataframe["roc_24"]

        dataframe["long_quality"] = (
            dataframe["target_bull_trend"].astype(int) * 3
            + dataframe["btc_allows_long"].astype(int)
            + (dataframe["relative_strength"] > 0.012).astype(int)
            + (dataframe["close"] > dataframe["high_55"] * (1.0 + dataframe["breakout_buffer_pct"])).astype(int) * 2
            + (dataframe["volume_ratio_24"] > 1.35).astype(int)
            + (dataframe["adx"] > 18).astype(int)
            + (dataframe["rsi"].between(54, 76)).astype(int)
        )
        dataframe["short_quality"] = (
            dataframe["target_bear_trend"].astype(int) * 3
            + dataframe["btc_allows_short"].astype(int)
            + (dataframe["relative_weakness"] > 0.012).astype(int)
            + (dataframe["close"] < dataframe["low_55"] * (1.0 - dataframe["breakout_buffer_pct"])).astype(int) * 2
            + (dataframe["volume_ratio_24"] > 1.35).astype(int)
            + (dataframe["adx"] > 18).astype(int)
            + (dataframe["rsi"].between(24, 46)).astype(int)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_breakout = (
            dataframe["target_bull_trend"]
            & dataframe["btc_allows_long"]
            & dataframe["volatility_ok"]
            & dataframe["volume_ok"]
            & (dataframe["close"] > dataframe["high_55"] * (1.0 + dataframe["breakout_buffer_pct"]))
            & (dataframe["close"] > dataframe["high_110"] * 0.990)
            & (dataframe["rsi"].between(54, 76))
            & (dataframe["adx"] > 18)
            & (dataframe["long_quality"] >= 7)
        )
        short_breakdown = (
            dataframe["target_bear_trend"]
            & dataframe["btc_allows_short"]
            & dataframe["volatility_ok"]
            & dataframe["volume_ok"]
            & (dataframe["close"] < dataframe["low_55"] * (1.0 - dataframe["breakout_buffer_pct"]))
            & (dataframe["close"] < dataframe["low_110"] * 1.010)
            & (dataframe["rsi"].between(24, 46))
            & (dataframe["adx"] > 18)
            & (dataframe["short_quality"] >= 7)
        )

        dataframe.loc[long_breakout, ["enter_long", "enter_tag"]] = (1, "sprint_v1_long_breakout")
        dataframe.loc[short_breakdown, ["enter_short", "enter_tag"]] = (1, "sprint_v1_short_breakdown")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_long = (
            (dataframe["close"] < dataframe["ema_50"])
            | (dataframe["close"] < dataframe["low_24"])
            | (
                (dataframe["btc_roc_24_1h"] < -0.055)
                & (dataframe["btc_rsi_1h"] < 38)
            )
            | (
                (dataframe["rsi"] < 42)
                & (dataframe["roc_6"] < -0.020)
            )
        )
        exit_short = (
            (dataframe["close"] > dataframe["ema_50"])
            | (dataframe["close"] > dataframe["high_24"])
            | (
                (dataframe["btc_roc_24_1h"] > 0.055)
                & (dataframe["btc_rsi_1h"] > 68)
            )
            | (
                (dataframe["rsi"] > 58)
                & (dataframe["roc_6"] > 0.020)
            )
        )

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = (1, "sprint_v1_long_signal_exit")
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = (1, "sprint_v1_short_signal_exit")
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
        if age_hours >= 24 * 7 and current_profit < 0.05:
            return "sprint_v1_stale_trade_exit"

        if current_profit < -0.16 and age_hours <= 24:
            if trade.is_short and float(last.get("close", current_rate)) > float(last.get("ema_24", current_rate)):
                return "sprint_v1_failed_short_fast_exit"
            if not trade.is_short and float(last.get("close", current_rate)) < float(last.get("ema_24", current_rate)):
                return "sprint_v1_failed_long_fast_exit"

        try:
            best_rate = trade.min_rate if trade.is_short else trade.max_rate
            max_profit = trade.calc_profit_ratio(best_rate)
        except Exception:
            max_profit = current_profit

        if max_profit > 0.45 and current_profit < max_profit * 0.55:
            return "sprint_v1_profit_retrace_exit"
        if max_profit > 0.25 and current_profit < 0.06:
            return "sprint_v1_breakeven_guard_exit"

        if current_profit > 0.20:
            if trade.is_short and float(last.get("close", current_rate)) > float(last.get("ema_24", current_rate)):
                return "sprint_v1_short_trailing_exit"
            if not trade.is_short and float(last.get("close", current_rate)) < float(last.get("ema_24", current_rate)):
                return "sprint_v1_long_trailing_exit"
        return None

    def _setup_quality(self, pair: str, side: str) -> tuple[float, float, bool]:
        last = self._last_analyzed_row(pair)
        if last is None:
            return 0.0, 0.03, False
        atr_pct = float(last.get("atr_pct", 0.03) or 0.03)
        if side == "short":
            quality = float(last.get("short_quality", 0) or 0)
            allowed = bool(last.get("target_bear_trend", False)) and bool(last.get("btc_allows_short", False))
        else:
            quality = float(last.get("long_quality", 0) or 0)
            allowed = bool(last.get("target_bull_trend", False)) and bool(last.get("btc_allows_long", False))
        if not bool(last.get("volatility_ok", False)) or not bool(last.get("volume_ok", False)):
            allowed = False
            quality -= 2.0
        return quality, atr_pct, allowed

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
        quality, atr_pct, allowed = self._setup_quality(pair, side)
        if not allowed:
            fraction = 0.08
        elif quality >= 9 and atr_pct < 0.035:
            fraction = self.strong_stake_fraction
        elif quality >= 7 and atr_pct < 0.060:
            fraction = self.base_stake_fraction
        else:
            fraction = 0.08

        if atr_pct > 0.055:
            fraction *= 0.60
        if atr_pct > 0.075:
            fraction *= 0.45

        risk_scale = float(self.config.get("sprint_risk_scale", 1.0))
        fraction *= max(0.20, min(risk_scale, 1.20))

        stake = proposed_stake * max(0.04, min(fraction, self.max_stake_fraction))
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
            if spread > 0.0020:
                return False
            if side == "long" and rate > ask * 1.0025:
                return False
            if side == "short" and rate < bid * 0.9975:
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
        configured_leverage = float(self.config.get("strategy_leverage", 10.0))
        quality, atr_pct, allowed = self._setup_quality(pair, side)
        leverage = min(configured_leverage, 10.0)
        if not allowed:
            leverage = min(leverage, 3.0)
        elif quality >= 9 and atr_pct < 0.030:
            leverage = min(leverage, 10.0)
        elif quality >= 8 and atr_pct < 0.045:
            leverage = min(leverage, 8.0)
        elif quality >= 7:
            leverage = min(leverage, 6.0)
        else:
            leverage = min(leverage, 4.0)

        if atr_pct > 0.055:
            leverage = min(leverage, 4.0)
        if atr_pct > 0.075:
            leverage = min(leverage, 2.0)
        return max(1.0, min(leverage, max_leverage))
