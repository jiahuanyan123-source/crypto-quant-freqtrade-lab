# Public Results Summary

Generated for public repository cleanup on 2026-06-03.

This file summarizes selected historical research evidence. It is not investment advice and does not claim future profitability.

## Main Strategy: EthBtcTrendCompound4hV4

Historical Freqtrade backtest:

- Strategy: `EthBtcTrendCompound4hV4`
- Market focus: ETH/BTC trend-compound logic on OKX futures data
- Timeframe: 4h
- Sample window: 2020-04-10 to 2026-05-01
- Reported historical return: +1893.27%
- Maximum drawdown: 17.90%

Interpretation:

The V4 result is the strongest current research record in the project, but it is still a historical backtest. It must not be treated as proof that the strategy will continue to work. The public value of this result is the engineering workflow: strategy logic, risk constraints, reproducibility discipline, and comparison against weaker variants.

## Dry-Run Status

Dry-run status observed on 2026-06-03:

- V4 bot stack was confirmed runnable locally.
- Dry-run database had 0 trades and 0 orders at the time of the handoff.
- This is consistent with a selective strategy, but it also means no live or dry-run profitability claim can be made yet.

## Rejected or Non-Promoted Experiments

### MomentumSprint1hV1

- Sample window: 2025-01-01 to 2026-06-03
- Historical return: -46.90%
- Maximum drawdown: 48.93%
- Sharpe: -1.05
- Trades: 114
- Status: rejected

Reason: too much noise, poor risk-adjusted behavior, and unacceptable drawdown.

### MomentumSprint1hV2

- Sample window: 2025-01-01 to 2026-06-03
- Historical return: -7.28%
- Maximum drawdown: 7.72%
- Sharpe: -0.66
- Trades: 64
- Recent sample window: 2026-04-01 to 2026-06-03
- Recent historical return: -0.10%
- Recent maximum drawdown: 0.55%
- Recent trades: 8
- Status: research only

Reason: V2 improved risk control versus V1, but it still lacks positive evidence.

### EthBtcRegimeTrend4hV5

- Full sample window: 2020-04-10 to 2026-06-03
- Historical return: +208.10%
- Maximum drawdown: 25.11%
- Trades: 59
- Profit factor: 1.71
- Recent sample window: 2026-04-01 to 2026-06-03
- V5 recent historical return: +27.47%
- V4 recent historical return over comparable period: +67.09%
- Status: not promoted

Reason: V5 increased activity but reduced quality relative to V4. More trades were not automatically better.

### MultiAssetRegimeTrend4hV1

- Sample window: 2025-01-01 to 2026-06-03
- Historical return: +6.83%
- Maximum drawdown: 18.24%
- Trades: 28
- Win rate: 57.1%
- Profit factor: 1.22
- V4 same-period reference return: +67.09%
- V4 same-period reference maximum drawdown: 17.90%
- Recent sample window: 2026-04-01 to 2026-06-03
- Recent historical return: +5.52%
- Recent maximum drawdown: 1.76%
- Status: not promoted

Reason: broad multi-asset rotation increased opportunities but diluted the V4 edge. This path needs stricter pair selection or relative-strength ranking before it deserves another promotion test.

## Moonshot Watchlist

Latest included report:

- File: `ft_userdata/user_data/reports/moonshot_watchlist_latest.md`
- Generated UTC: 2026-06-03T05:58:24
- Scanned pairs: 30
- Pairs with stale data older than 48 hours: 15

Interpretation:

The watchlist is a high-risk opportunity radar. It is not a trading signal, not a prediction engine, and not a profit claim.

## Verification Run During Public Cleanup

The following syntax check was run for the core public files:

```powershell
python -m py_compile `
  user_data\strategies\EthBtcTrendCompound4hV4.py `
  user_data\strategies\MomentumSprint1hV1.py `
  user_data\strategies\MomentumSprint1hV2.py `
  user_data\tools\moonshot_watchlist_v1.py
```

Result: passed.

## Public-Safety Exclusions

The repository intentionally excludes:

- raw exchange data
- logs
- SQLite databases
- zipped backtest results
- local API passwords and tokens
- real live-trading configuration
- generated runtime state

These exclusions are part of the public evidence standard. A portfolio project should be inspectable without leaking secrets or pretending that private runtime artifacts are reproducible research.

## Open Gaps

- Add CI for syntax checks.
- Add a reproducible data download guide.
- Add walk-forward validation commands and a compact table of results.
- Publish to GitHub only after the staged file list is verified.
