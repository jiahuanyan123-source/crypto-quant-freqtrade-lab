from datetime import datetime
from typing import Optional

from pandas import DataFrame

from EthBtcTrendCompound4hV4 import EthBtcTrendCompound4hV4


class EthBtcRegimeTrend4hV5(EthBtcTrendCompound4hV4):
    """
    ETH/BTC 4h regime trend strategy.

    V4 is intentionally long-only and very selective. V5 keeps the same slow
    regime idea, but adds a short side for confirmed bear regimes and relaxes
    long entries from pure 120-candle breakouts to controlled trend continuation.
    """

    can_short = True
    stoploss = -0.30

    defensive_stake_fraction = 0.10
    base_stake_fraction = 0.18
    strong_stake_fraction = 0.26
    max_stake_fraction = 0.32

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)

        dataframe["major_bear_regime"] = (
            (dataframe["close"] < dataframe["ema_200"])
            & (dataframe["ema_50"] < dataframe["ema_200"])
            & (dataframe["ema_100"] < dataframe["ema_200"])
            & (dataframe["roc_180"] < 0)
            & (dataframe["btc_close_4h"] < dataframe["btc_ema_200_4h"])
            & (dataframe["btc_ema_50_4h"] < dataframe["btc_ema_200_4h"])
            & (dataframe["btc_ema_100_4h"] < dataframe["btc_ema_200_4h"])
            & (dataframe["btc_roc_180_4h"] < 0)
        )
        dataframe["bear_quality"] = (
            dataframe["major_bear_regime"].astype(int) * 4
            + (dataframe["close"] < dataframe["ema_50"]).astype(int)
            + (dataframe["ema_20"] < dataframe["ema_50"]).astype(int)
            + (dataframe["btc_close_4h"] < dataframe["btc_ema_50_4h"]).astype(int)
            + (dataframe["btc_ema_20_4h"] < dataframe["btc_ema_50_4h"]).astype(int)
            + (dataframe["roc_84"] < 0).astype(int)
            + (dataframe["btc_roc_84_4h"] < 0).astype(int)
            + (dataframe["roc_126"] < -0.040).astype(int)
            + (dataframe["btc_roc_126_4h"] < -0.015).astype(int)
            + (dataframe["adx"] > 15).astype(int)
        )
        dataframe["bear_panic_too_late"] = (
            ((dataframe["roc_42"] < -0.220) & (dataframe["rsi"] < 22))
            | ((dataframe["btc_roc_42_4h"] < -0.180) & (dataframe["btc_rsi_4h"] < 20))
        )
        dataframe["bear_breakdown"] = (
            (dataframe["close"] < dataframe["low_55"])
            | (
                (dataframe["close"] < dataframe["ema_20"])
                & (dataframe["roc_42"] < -0.055)
                & (dataframe["btc_roc_42_4h"] < -0.035)
            )
        )
        dataframe["bull_continuation"] = (
            dataframe["confirmed_breakout"]
            | (
                (dataframe["close"] > dataframe["ema_20"])
                & (dataframe["ema_20"] > dataframe["ema_50"])
                & (dataframe["roc_42"] > 0.045)
                & (dataframe["btc_roc_42_4h"] > 0.020)
                & (dataframe["volume_ratio"] > 0.80)
            )
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if metadata["pair"] != "ETH/USDT:USDT":
            return dataframe

        long_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["volume_ratio"] > 0.70)
            & dataframe["major_bull_regime"]
            & dataframe["volatility_ok"]
            & (~dataframe["panic_filter"])
            & (~dataframe["overheated"])
            & dataframe["bull_continuation"]
            & (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["btc_close_4h"] > dataframe["btc_ema_50_4h"])
            & (dataframe["rsi"].between(50, 74))
            & (dataframe["trend_quality"] >= 9)
        )

        short_entry = (
            (dataframe["volume"] > 0)
            & (dataframe["volume_ratio"] > 0.75)
            & dataframe["major_bear_regime"]
            & dataframe["volatility_ok"]
            & (~dataframe["bear_panic_too_late"])
            & dataframe["bear_breakdown"]
            & (dataframe["close"] < dataframe["ema_50"])
            & (dataframe["btc_close_4h"] < dataframe["btc_ema_50_4h"])
            & (dataframe["rsi"].between(22, 52))
            & (dataframe["bear_quality"] >= 9)
        )

        dataframe.loc[long_entry, ["enter_long", "enter_tag"]] = (1, "v5_long_regime_trend")
        dataframe.loc[short_entry, ["enter_short", "enter_tag"]] = (1, "v5_short_regime_trend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_long = (
            (dataframe["close"] < dataframe["low_55"])
            | (
                (dataframe["btc_close_4h"] < dataframe["btc_ema_200_4h"])
                & (dataframe["btc_roc_42_4h"] < 0)
            )
            | (
                (dataframe["close"] < dataframe["ema_100"])
                & (dataframe["roc_42"] < -0.030)
            )
            | (
                (dataframe["close"] < dataframe["ema_50"])
                & (dataframe["btc_close_4h"] < dataframe["btc_ema_50_4h"])
            )
        )

        exit_short = (
            (dataframe["close"] > dataframe["high_120"])
            | (
                (dataframe["btc_close_4h"] > dataframe["btc_ema_200_4h"])
                & (dataframe["btc_roc_42_4h"] > 0)
            )
            | (
                (dataframe["close"] > dataframe["ema_100"])
                & (dataframe["roc_42"] > 0.030)
            )
            | (
                (dataframe["close"] > dataframe["ema_50"])
                & (dataframe["btc_close_4h"] > dataframe["btc_ema_50_4h"])
            )
        )

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = (1, "v5_long_trend_exit")
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = (1, "v5_short_trend_exit")
        return dataframe

    def _setup_quality_by_side(self, pair: str, side: str) -> tuple[float, float, float, bool]:
        last = self._last_analyzed_row(pair)
        if last is None:
            return 0.0, 0.03, 0.03, False

        atr_pct = float(last.get("atr_pct", 0.03) or 0.03)
        btc_atr_pct = float(last.get("btc_atr_pct_4h", 0.03) or 0.03)

        if side == "short":
            quality = float(last.get("bear_quality", 0) or 0)
            allowed = bool(last.get("major_bear_regime", False)) and bool(last.get("volatility_ok", False))
            if bool(last.get("bear_panic_too_late", False)):
                allowed = False
                quality -= 2.0
        else:
            quality = float(last.get("trend_quality", 0) or 0)
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
        quality, atr_pct, btc_atr_pct, allowed = self._setup_quality_by_side(pair, side)
        if not allowed:
            fraction = self.defensive_stake_fraction
        elif quality >= 12 and atr_pct < 0.040 and btc_atr_pct < 0.032:
            fraction = self.strong_stake_fraction
        elif quality >= 10 and atr_pct < 0.058:
            fraction = self.base_stake_fraction
        else:
            fraction = self.defensive_stake_fraction

        if side == "short":
            fraction *= 0.85
        if atr_pct > 0.060 or btc_atr_pct > 0.046:
            fraction *= 0.70

        risk_scale = float(self.config.get("regime4h_risk_scale", self.config.get("compound4h_risk_scale", 1.0)))
        fraction *= max(0.25, min(risk_scale, 1.35))

        stake = proposed_stake * max(0.06, min(fraction, self.max_stake_fraction))
        if min_stake:
            stake = max(stake, min_stake)
        return min(stake, max_stake)

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
            quality, atr_pct, btc_atr_pct, allowed = self._setup_quality_by_side(pair, side)
            if not allowed:
                leverage = min(leverage, 1.5)
            elif quality >= 12 and atr_pct < 0.040 and btc_atr_pct < 0.032:
                leverage = min(leverage, 4.0)
            elif quality >= 10 and atr_pct < 0.058:
                leverage = min(leverage, 3.0)
            else:
                leverage = min(leverage, 2.0)
            if side == "short":
                leverage = min(leverage, 3.0)
            if atr_pct > 0.060 or btc_atr_pct > 0.046:
                leverage = min(leverage, 2.0)
        except Exception:
            leverage = min(configured_leverage, 1.5)
        return max(1.0, min(leverage, max_leverage))
