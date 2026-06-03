# Multi-Asset Regime Trend 4h V1 Status

Generated: 2026-06-03

## Purpose

This candidate was created to test a specific hypothesis:

V4 may be strong not because it trades ETH only, but because it waits for confirmed 4h risk-on regimes. If that edge generalizes, a multi-asset version could rotate into liquid coins with stronger trend continuation and create more opportunities without forcing ETH shorts.

## Files

- Public strategy implementation: `user_data/strategies/MultiAssetRegimeTrend4hV1.py`
- Local research config: `user_data/config_multi_asset_regime_trend_4h_v1_dryrun.json`
- Local research compose file: `docker-compose.multi-asset-regime-trend-4h-v1-dryrun.yml`

The local config and compose file are not part of the first public baseline. This status document is included to preserve the research conclusion, not to promote V1 as a runnable bot.

## Validation

Basic checks passed:

- Python compile check passed.
- Config JSON parse check passed.
- Freqtrade `list-strategies` recognized `MultiAssetRegimeTrend4hV1`.

## Data Preparation

On 2026-06-03, 4h futures data was refreshed for the configured OKX futures whitelist:

- BTC, ETH, SOL, XRP, DOGE, BNB, LINK, AVAX, NEAR, ADA, SUI, PEPE, WIF, BONK, FLOKI.
- Most 4h futures pairs now cover 2024-01-01 to 2026-06-03.
- WIF starts at 2024-04-15.
- BONK starts at 2024-01-08.

Important limitation:

- Funding-rate data is still mostly available only from late 2026-01 onward in the local OKX dataset. V1 does not use funding as an entry edge, so the 4h trend test remains usable, but the futures-cost history is incomplete for older periods.

## Backtest Results

All backtests below used official Freqtrade backtesting with:

- Isolated futures mode.
- Fee: 0.05%.
- Protections enabled.
- `--cache none` after data refresh.

### Main Recent Period

Timerange: 2025-01-01 to 2026-06-03

- Total return: +6.83%
- Max drawdown: 18.24%
- Trades: 28
- Win rate: 57.1%
- Profit factor: 1.22
- CAGR: 4.76%
- Daily wallet Sharpe: 0.38

V4 same-period reference, rerun on 2026-06-03:

- Total return: +67.09%
- Max drawdown: 17.90%
- Trades: 6
- Win rate: 50.0%
- Profit factor: 2.22
- Daily wallet Sharpe: 0.84

### Recent 2-Month Check

Timerange: 2026-04-01 to 2026-06-03

- Total return: +5.52%
- Max drawdown: 1.76%
- Trades: 7
- Win rate: 71.4%
- Profit factor: 3.16

This short window is encouraging operationally, but it is not enough to promote the strategy. The longer 2025-2026 result is much weaker than V4.

## Verdict

V1 is not promoted.

The broad multi-asset whitelist increased trade count, but it did not improve the system. After proper data refresh, the first cached result was invalid; the real recomputed result showed that extra altcoin activity diluted the edge and introduced more stop-loss losses.

Current conclusion:

- Keep `EthBtcTrendCompound4hV4.py` as the only active dry-run strategy.
- Do not start `MultiAssetRegimeTrend4hV1` as a bot.
- Do not assume broad multi-asset rotation improves V4.
- If this path is revisited, it needs stricter pair selection and relative-strength ranking, not a static large whitelist.

## Durable Lessons

1. Always check data coverage before trusting a multi-pair backtest.
2. After refreshing data, rerun backtests with `--cache none`; otherwise Freqtrade may reuse stale results.
3. More pairs can make the strategy worse by adding weaker setups and more stop-loss events.
4. A short recent win is not enough to override a poor longer recent-period comparison against V4.
