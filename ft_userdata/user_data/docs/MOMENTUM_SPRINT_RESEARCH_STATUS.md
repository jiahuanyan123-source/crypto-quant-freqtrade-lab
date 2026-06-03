# Momentum Sprint Research Status

Generated: 2026-06-03

## Purpose

This branch of the project is the high-risk second layer: a small-capital, higher-leverage futures sprint strategy for long/short crypto momentum. It is separate from the steadier 4h ETH trend strategy.

## Files

- `user_data/strategies/MomentumSprint1hV1.py`
- `user_data/strategies/MomentumSprint1hV2.py`
- `user_data/config_momentum_sprint_1h_v1_dryrun.json`
- `user_data/config_momentum_sprint_1h_v2_dryrun.json`
- `docker-compose.momentum-sprint-1h-v1-dryrun.yml`
- `docker-compose.momentum-sprint-1h-v2-dryrun.yml`
- `user_data/tools/moonshot_watchlist_v1.py`
- `user_data/reports/moonshot_watchlist_latest.md`
- `user_data/reports/moonshot_watchlist_latest.json`

## Backtest Results

### MomentumSprint1hV1

Timerange: 2025-01-01 to 2026-06-03

- Total return: -46.90%
- Max drawdown: 48.93%
- Sharpe: -1.05
- Trades: 114
- Win rate: 36.8%
- Long result: -15.18%
- Short result: -31.72%

Verdict: rejected. Too much loss from failed breakouts and stoploss exits.

### MomentumSprint1hV2

Timerange: 2025-01-01 to 2026-06-03

- Total return: -7.28%
- Max drawdown: 7.72%
- Sharpe: -0.66
- Trades: 64
- Win rate: 28.1%
- Long result: -5.87%
- Short result: -1.41%

Timerange: 2026-04-01 to 2026-06-03

- Total return: -0.10%
- Max drawdown: 0.55%
- Sharpe: -0.07
- Trades: 8
- Win rate: 50.0%
- Long result: +0.50%
- Short result: -0.60%

Verdict: research only. V2 controls risk much better than V1, but it still does not prove positive expectancy.

## Current Decision

Do not start MomentumSprint V1 or V2 as a dry-run trading bot. The watchlist tool may be used for market scanning, but the automatic strategy is not yet qualified.

The next useful research step is not more blind parameter tuning. It should be one of:

- Build a baseline trend strategy on 4h/1d multi-asset futures and compare it against this 1h sprint layer.
- Add a market-wide regime model before allowing any sprint trades.
- Use the watchlist as a human-reviewed paper trading queue and collect forward results before adding automation.
