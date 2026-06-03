from datetime import datetime
from typing import Optional

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, merge_informative_pair


class EthBtcTrendCompound4hV4(IStrategy):
    """
    ETH 4h long-only trend compounding strategy, confirmed-breakout version.

    Core edge:
    - Stay flat most of the time.
    - Only buy ETH perpetuals when both BTC and ETH confirm a major bull regime.
    - Use adaptive position size and leverage instead of trying to predict every candle.

    V4 keeps V3's main regime logic and makes one conservative change:
    - A breakout must clear the previous 120-candle high by a small ATR-based buffer.
    - Volume confirmation is slightly stricter.

    Dry-run / research only. No strategy can guarantee profit.
    """

    INTERFACE_VERSION = 3

    can_short = False
    timeframe = "4h"
    startup_candle_count = 600
    process_only_new_candles = True

    minimal_roi = {"0": 10.0}
    stoploss = -0.40

    trailing_stop = False
    use_custom_stoploss = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    position_adjustment_enable = False

    defensive_stake_fraction = 0.14
    base_stake_fraction = 0.23
    strong_stake_fraction = 0.32
    max_stake_fraction = 0.38

    min_breakout_volume_ratio = 0.60
    breakout_atr_fraction = 0.10
    min_breakout_buffer_pct = 0.0015
    max_breakout_buffer_pct = 0.0060

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
                "lookback_period_candles": 6 * 60,
                "trade_limit": 2,
                "stop_duration_candles": 6 * 14,
                "only_per_pair": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 6 * 210,
                "trade_limit": 5,
                "stop_duration_candles": 6 * 28,
                "max_allowed_drawdown": 0.30,
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
        dataframe[f"{prefix}roc_42"] = ta.ROC(dataframe, timeperiod=42) / 100.0
        dataframe[f"{prefix}roc_84"] = ta.ROC(dataframe, timeperiod=84) / 100.0
        dataframe[f"{prefix}roc_126"] = ta.ROC(dataframe, timeperiod=126) / 100.0
        dataframe[f"{prefix}roc_180"] = ta.ROC(dataframe, timeperiod=180) / 100.0
        dataframe[f"{prefix}volume_mean_30"] = dataframe["volume"].rolling(30).mean()
        dataframe[f"{prefix}volume_ratio"] = dataframe["volume"] / dataframe[f"{prefix}volume_mean_30"]
        dataframe[f"{prefix}high_120"] = dataframe["high"].rolling(120).max().shift(1)
        dataframe[f"{prefix}high_150"] = dataframe["high"].rolling(150).max().shift(1)
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
                    "btc_roc_42",
                    "btc_roc_84",
                    "btc_roc_126",
                    "btc_roc_180",
                ]
            ]
            dataframe = merge_informative_pair(dataframe, btc, self.timeframe, "4h", ffill=True)

        dataframe["major_bull_regime"] = (
            (dataframe["close"] > dataframe["ema_200"])
            & (dataframe["ema_50"] > dataframe["ema_200"])
            & (dataframe["ema_100"] > dataframe["ema_200"])
            & (dataframe["roc_180"] > 0)
            & (dataframe["btc_close_4h"] > dataframe["btc_ema_200_4h"])
            & (dataframe["btc_ema_50_4h"] > dataframe["btc_ema_200_4h"])
            & (dataframe["btc_ema_100_4h"] > dataframe["btc_ema_200_4h"])
            & (dataframe["btc_roc_180_4h"] > 0)
        )
        dataframe["trend_quality"] = (
            dataframe["major_bull_regime"].astype(int) * 4
            + (dataframe["close"] > dataframe["ema_50"]).astype(int)
            + (dataframe["ema_20"] > dataframe["ema_50"]).astype(int)
            + (dataframe["btc_close_4h"] > dataframe["btc_ema_50_4h"]).astype(int)
            + (dataframe["btc_ema_20_4h"] > dataframe["btc_ema_50_4h"]).astype(int)
            + (dataframe["roc_84"] > 0).astype(int)
            + (dataframe["btc_roc_84_4h"] > 0).astype(int)
            + (dataframe["roc_126"] > 0.04).astype(int)
            + (dataframe["btc_roc_126_4h"] > 0.015).astype(int)
            + (dataframe["adx"] > 15).astype(int)
        )
        dataframe["volatility_ok"] = (
            (dataframe["atr_pct"] > 0.006)
            & (dataframe["atr_pct"] < 0.085)
            & (dataframe["atr_pct"] < dataframe["atr_pct_median_90d"] * 1.85)
            & (dataframe["btc_atr_pct_4h"] < dataframe["btc_atr_pct_median_90d_4h"] * 1.90)
        )
        dataframe["panic_filter"] = (
            ((dataframe["roc_42"] < -0.130) & (dataframe["rsi"] < 38))
            | ((dataframe["btc_roc_42_4h"] < -0.110) & (dataframe["btc_rsi_4h"] < 40))
        )
        dataframe["overheated"] = (
            (dataframe["rsi"] > 78)
            | ((dataframe["roc_42"] > 0.260) & (dataframe["range_pct"] > dataframe["atr_pct_median_90d"] * 1.65))
        )
        dataframe["breakout_buffer_pct"] = (dataframe["atr_pct"] * self.breakout_atr_fraction).clip(
            lower=self.min_breakout_buffer_pct,
            upper=self.max_breakout_buffer_pct,
        )
        dataframe["confirmed_breakout"] = dataframe["close"] > (
            dataframe["high_120"] * (1.0 + dataframe["breakout_buffer_pct"])
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if metadata["pair"] != "ETH/USDT:USDT":
            return dataframe

        breakout = (
            (dataframe["volume"] > 0)
            & (dataframe["volume_ratio"] > self.min_breakout_volume_ratio)
            & dataframe["major_bull_regime"]
            & dataframe["volatility_ok"]
            & (~dataframe["panic_filter"])
            & (~dataframe["overheated"])
            & dataframe["confirmed_breakout"]
            & (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["btc_close_4h"] > dataframe["btc_ema_50_4h"])
            & (dataframe["rsi"] > 52)
            & (dataframe["trend_quality"] >= 9)
        )

        dataframe.loc[breakout, ["enter_long", "enter_tag"]] = (1, "compound4h_v4_confirmed_bull")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_long = (
            (dataframe["close"] < dataframe["low_55"])
            | (
                (dataframe["btc_close_4h"] < dataframe["btc_ema_200_4h"])
                & (dataframe["btc_roc_42_4h"] < 0)
            )
            | (
                (dataframe["close"] < dataframe["ema_200"])
                & (dataframe["roc_42"] < 0)
            )
            | (
                (dataframe["close"] < dataframe["ema_100"])
                & (dataframe["btc_close_4h"] < dataframe["btc_ema_100_4h"])
                & (dataframe["roc_42"] < -0.050)
            )
        )

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = (1, "compound4h_v4_trend_exit")
        return dataframe

    def _last_analyzed_row(self, pair: str):
        if not self.dp:
            return None
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        return dataframe.iloc[-1]

    def _setup_quality(self, pair: str) -> tuple[float, float, float, bool]:
        last = self._last_analyzed_row(pair)
        if last is None:
            return 0.0, 0.03, 0.03, False

        quality = float(last.get("trend_quality", 0) or 0)
        atr_pct = float(last.get("atr_pct", 0.03) or 0.03)
        btc_atr_pct = float(last.get("btc_atr_pct_4h", 0.03) or 0.03)
        allowed = bool(last.get("major_bull_regime", False)) and bool(last.get("volatility_ok", False))
        if bool(last.get("panic_filter", False)) or bool(last.get("overheated", False)):
            allowed = False
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
        elif quality >= 12 and atr_pct < 0.040 and btc_atr_pct < 0.032:
            fraction = self.strong_stake_fraction
        elif quality >= 10 and atr_pct < 0.058:
            fraction = self.base_stake_fraction
        else:
            fraction = self.defensive_stake_fraction

        if atr_pct > 0.060 or btc_atr_pct > 0.046:
            fraction *= 0.70

        risk_scale = float(self.config.get("compound4h_risk_scale", 1.0))
        fraction *= max(0.25, min(risk_scale, 1.35))

        stake = proposed_stake * max(0.08, min(fraction, self.max_stake_fraction))
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
            if spread > 0.0015:
                return False
            if rate > ask * 1.0020:
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
        configured_leverage = float(self.config.get("strategy_leverage", 5.0))
        leverage = min(configured_leverage, 5.0)
        try:
            quality, atr_pct, btc_atr_pct, allowed = self._setup_quality(pair)
            if not allowed:
                leverage = min(leverage, 2.0)
            elif quality >= 12 and atr_pct < 0.040 and btc_atr_pct < 0.032:
                leverage = min(leverage, 5.0)
            elif quality >= 10 and atr_pct < 0.058:
                leverage = min(leverage, 4.0)
            else:
                leverage = min(leverage, 3.0)
            if atr_pct > 0.060 or btc_atr_pct > 0.046:
                leverage = min(leverage, 2.5)
        except Exception:
            leverage = min(configured_leverage, 2.0)
        return max(1.0, min(leverage, max_leverage))
