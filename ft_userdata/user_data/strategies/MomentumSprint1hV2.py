from datetime import datetime
from typing import Optional

from pandas import DataFrame

from freqtrade.persistence import Trade

from MomentumSprint1hV1 import MomentumSprint1hV1


class MomentumSprint1hV2(MomentumSprint1hV1):
    """
    More selective version of MomentumSprint1hV1.

    V1 proved that large winners exist, but the strategy bled too much on failed
    breakouts. V2 tightens loss control and only enters stronger momentum setups.
    """

    stoploss = -0.12

    base_stake_fraction = 0.08
    strong_stake_fraction = 0.14
    max_stake_fraction = 0.18

    @property
    def protections(self) -> list[dict]:
        return [
            {
                "method": "CooldownPeriod",
                "stop_duration_candles": 6,
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 72,
                "trade_limit": 1,
                "stop_duration_candles": 72,
                "only_per_pair": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 24 * 30,
                "trade_limit": 5,
                "stop_duration_candles": 24 * 10,
                "max_allowed_drawdown": 0.20,
            },
        ]

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        not_too_extended_long = dataframe["close"] < dataframe["ema_24"] * (
            1.0 + dataframe["atr_pct"].clip(0.01, 0.05) * 4.0
        )
        not_too_extended_short = dataframe["close"] > dataframe["ema_24"] * (
            1.0 - dataframe["atr_pct"].clip(0.01, 0.05) * 4.0
        )

        long_breakout = (
            dataframe["target_bull_trend"]
            & dataframe["btc_allows_long"]
            & dataframe["volatility_ok"]
            & dataframe["volume_ok"]
            & (dataframe["range_pct"] < dataframe["atr_pct"] * 2.8)
            & (dataframe["close"] > dataframe["high_55"] * (1.0 + dataframe["breakout_buffer_pct"]))
            & (dataframe["close"] > dataframe["high_110"] * 0.995)
            & (dataframe["roc_6"] > 0.006)
            & (dataframe["roc_24"] > 0.025)
            & (dataframe["relative_strength"] > 0.020)
            & (dataframe["volume_ratio_24"] > 1.30)
            & (dataframe["rsi"].between(58, 72))
            & (dataframe["adx"] > 25)
            & (dataframe["long_quality"] >= 10)
            & (dataframe["btc4_close_4h"] > dataframe["btc4_ema_200_4h"])
            & (dataframe["btc_roc_72_1h"] > 0.010)
            & not_too_extended_long
        )

        short_breakdown = (
            dataframe["target_bear_trend"]
            & dataframe["btc_allows_short"]
            & dataframe["volatility_ok"]
            & dataframe["volume_ok"]
            & (dataframe["range_pct"] < dataframe["atr_pct"] * 2.8)
            & (dataframe["close"] < dataframe["low_55"] * (1.0 - dataframe["breakout_buffer_pct"]))
            & (dataframe["close"] < dataframe["low_110"] * 1.005)
            & (dataframe["roc_6"] < -0.006)
            & (dataframe["roc_24"] < -0.025)
            & (dataframe["relative_weakness"] > 0.025)
            & (dataframe["volume_ratio_24"] > 1.35)
            & (dataframe["rsi"].between(28, 42))
            & (dataframe["adx"] > 25)
            & (dataframe["short_quality"] >= 10)
            & (dataframe["btc4_close_4h"] < dataframe["btc4_ema_100_4h"])
            & (dataframe["btc_roc_72_1h"] < -0.010)
            & not_too_extended_short
        )

        dataframe.loc[long_breakout, ["enter_long", "enter_tag"]] = (1, "sprint_v2_long_momentum")
        dataframe.loc[short_breakdown, ["enter_short", "enter_tag"]] = (1, "sprint_v2_short_momentum")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_long = (
            (dataframe["close"] < dataframe["ema_24"])
            | (
                (dataframe["rsi"] < 46)
                & (dataframe["roc_6"] < -0.010)
            )
            | (
                (dataframe["btc_roc_24_1h"] < -0.045)
                & (dataframe["btc_rsi_1h"] < 40)
            )
        )
        exit_short = (
            (dataframe["close"] > dataframe["ema_24"])
            | (
                (dataframe["rsi"] > 54)
                & (dataframe["roc_6"] > 0.010)
            )
            | (
                (dataframe["btc_roc_24_1h"] > 0.045)
                & (dataframe["btc_rsi_1h"] > 65)
            )
        )

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = (1, "sprint_v2_long_signal_exit")
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = (1, "sprint_v2_short_signal_exit")
        return dataframe

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
        if age_hours >= 72 and current_profit < 0.08:
            return "sprint_v2_stale_trade_exit"

        if current_profit < -0.07:
            if trade.is_short:
                if float(last.get("close", current_rate)) > float(last.get("ema_12", current_rate)):
                    return "sprint_v2_failed_short_exit"
            else:
                if float(last.get("close", current_rate)) < float(last.get("ema_12", current_rate)):
                    return "sprint_v2_failed_long_exit"

        try:
            best_rate = trade.min_rate if trade.is_short else trade.max_rate
            max_profit = trade.calc_profit_ratio(best_rate)
        except Exception:
            max_profit = current_profit

        if max_profit > 0.30 and current_profit < max_profit * 0.55:
            return "sprint_v2_profit_retrace_exit"
        if max_profit > 0.18 and current_profit < 0.03:
            return "sprint_v2_breakeven_guard_exit"

        if current_profit > 0.12:
            if trade.is_short and float(last.get("close", current_rate)) > float(last.get("ema_12", current_rate)):
                return "sprint_v2_short_trailing_exit"
            if not trade.is_short and float(last.get("close", current_rate)) < float(last.get("ema_12", current_rate)):
                return "sprint_v2_long_trailing_exit"
        return None

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
            fraction = 0.04
        elif quality >= 11 and atr_pct < 0.030:
            fraction = self.strong_stake_fraction
        elif quality >= 9 and atr_pct < 0.055:
            fraction = self.base_stake_fraction
        else:
            fraction = 0.04

        if side == "short":
            fraction *= 0.80
        if atr_pct > 0.045:
            fraction *= 0.65
        if atr_pct > 0.065:
            fraction *= 0.45

        risk_scale = float(self.config.get("sprint_risk_scale", 1.0))
        fraction *= max(0.20, min(risk_scale, 1.20))

        stake = proposed_stake * max(0.025, min(fraction, self.max_stake_fraction))
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
        configured_leverage = float(self.config.get("strategy_leverage", 10.0))
        quality, atr_pct, allowed = self._setup_quality(pair, side)
        leverage = min(configured_leverage, 10.0)
        if not allowed:
            leverage = min(leverage, 2.0)
        elif quality >= 11 and atr_pct < 0.022:
            leverage = min(leverage, 10.0)
        elif quality >= 10 and atr_pct < 0.035:
            leverage = min(leverage, 8.0)
        elif quality >= 9:
            leverage = min(leverage, 6.0)
        else:
            leverage = min(leverage, 3.0)

        if side == "short":
            leverage = min(leverage, 6.0)
        if atr_pct > 0.045:
            leverage = min(leverage, 4.0)
        if atr_pct > 0.065:
            leverage = min(leverage, 2.0)
        return max(1.0, min(leverage, max_leverage))
