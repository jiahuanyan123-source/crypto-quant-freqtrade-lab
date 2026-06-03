# ETH/BTC Regime Trend 4h V5 Status

Generated: 2026-06-03

## Purpose

V5 was created to answer a specific operational problem:

V4 is alive and historically strong, but it is long-only and very selective. In the current bearish market it can sit flat for a long time. V5 tests whether adding a confirmed 4h short side and a less strict long continuation entry can create a more active trading bot without destroying robustness.

## Files

- `user_data/strategies/EthBtcRegimeTrend4hV5.py`
- `user_data/config_eth_btc_regime_trend_4h_v5_dryrun.json`
- `docker-compose.eth-btc-regime-trend-4h-v5-dryrun.yml`

## Validation

Basic checks passed:

- Python compile check passed.
- Config JSON parse check passed.
- Freqtrade `list-strategies` recognized `EthBtcRegimeTrend4hV5`.

## Backtest Results

### Full Available Period

Timerange: 2020-04-10 to 2026-06-03

- Total return: +208.10%
- Max drawdown: 25.11%
- Trades: 59
- Win rate: 37.3%
- Profit factor: 1.71
- Long result: +305.08%
- Short result: -96.98%

V4 reference full-period result previously recorded:

- Total return: +1893.27%
- Max drawdown: 17.90%

### Recent Period

Timerange: 2025-01-01 to 2026-06-03

- V5 total return: +27.47%
- V5 max drawdown: 18.41%
- V5 trades: 17
- V5 win rate: 35.3%
- V5 long result: +36.28%
- V5 short result: -8.81%

V4 same recent-period reference:

- V4 total return: +67.09%
- V4 max drawdown: 17.90%
- V4 trades: 6
- V4 win rate: 50.0%

## Verdict

V5 is not promoted.

It increases trade count, but the extra activity does not improve the strategy. The short side is the main weakness and remains negative in both full-period and recent-period tests.

Current conclusion:

- Keep V4 as the main dry-run strategy.
- Do not start V5 as a dry-run bot yet.
- Do not assume adding shorts improves the system.
- The next better path is likely multi-asset 4h trend selection or a stronger market-regime classifier, not simply enabling short trades.

## Durable Lesson

More trades are not automatically better. The project needs a tradable bot, but the bot must still preserve edge. V5 shows that forcing activity by adding shorts can reduce strategy quality.
