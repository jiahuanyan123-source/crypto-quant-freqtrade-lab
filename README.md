# Crypto Quant Freqtrade Lab

[![Python syntax check](https://github.com/jiahuanyan123-source/crypto-quant-freqtrade-lab/actions/workflows/python-syntax.yml/badge.svg)](https://github.com/jiahuanyan123-source/crypto-quant-freqtrade-lab/actions/workflows/python-syntax.yml)

This repository is a public-safe Freqtrade research lab for crypto quant strategy engineering.

The project focuses on:

- Freqtrade strategy implementation and experiment hygiene
- OKX futures dry-run workflows
- Backtest, walk-forward, and failure-case documentation
- Risk-aware research notes that separate evidence from speculation
- AI-assisted development discipline through Codex handoff notes and playbooks

This is not investment advice. The included backtest results are historical research records, not proof of future profitability.

## Current Status

Public cleanup baseline created on 2026-06-03.

The main promoted research path is `EthBtcTrendCompound4hV4`, a selective 4h ETH/BTC trend-compound strategy. Other strategies are kept as research artifacts or rejected experiments, because a useful portfolio should show how bad ideas were killed as well as how promising ideas were built.

## Repository Layout

```text
ft_userdata/
  docker-compose.eth-btc-trend-compound-4h-v4-dryrun.yml
  docker-compose.eth-btc-trend-compound-4h-v4-live.template.yml
  user_data/
    config_eth_btc_trend_compound_4h_v4_dryrun.json
    config_eth_btc_trend_compound_4h_v4_live.template.json
    docs/
    reports/
      moonshot_watchlist_latest.md
    strategies/
      EthBtcTrendCompound4hV4.py
      EthBtcRegimeTrend4hV5.py
      MomentumSprint1hV1.py
      MomentumSprint1hV2.py
      MultiAssetRegimeTrend4hV1.py
    tools/
docs/
  results_summary.md
```

Ignored by design:

- raw exchange data
- logs
- SQLite databases
- zipped backtest artifacts
- local API tokens and real trading configs
- generated model/runtime state

## Main Research Artifacts

- `ft_userdata/user_data/strategies/EthBtcTrendCompound4hV4.py`: main 4h ETH/BTC trend-compound strategy.
- `ft_userdata/user_data/docs/CODEX_MAXXING_CRYPTO_QUANT_PLAYBOOK.md`: operating playbook and research record.
- `ft_userdata/user_data/docs/MOMENTUM_SPRINT_RESEARCH_STATUS.md`: rejected momentum sprint experiment log.
- `ft_userdata/user_data/docs/ETH_BTC_REGIME_TREND_4H_V5_STATUS.md`: V5 comparison and non-promotion note.
- `ft_userdata/user_data/docs/MULTI_ASSET_REGIME_TREND_4H_V1_STATUS.md`: multi-asset rotation test and rejection note.
- `ft_userdata/user_data/tools/moonshot_watchlist_v1.py`: high-risk opportunity radar script.
- `docs/results_summary.md`: public summary of verified historical results and caveats.

## Minimal Workflow

Install and run Freqtrade using the official Freqtrade Docker workflow. Market data is intentionally not committed to this repository, so a fresh clone needs to download data before reproducing backtests.

Start the V4 dry-run stack:

```powershell
cd ft_userdata
docker compose -f docker-compose.eth-btc-trend-compound-4h-v4-dryrun.yml up -d
```

Compile the key Python files:

```powershell
python -m py_compile `
  user_data\strategies\EthBtcTrendCompound4hV4.py `
  user_data\strategies\MomentumSprint1hV1.py `
  user_data\strategies\MomentumSprint1hV2.py `
  user_data\tools\moonshot_watchlist_v1.py
```

Run the moonshot watchlist script:

```powershell
python user_data\tools\moonshot_watchlist_v1.py
```

Example backtest command after data is available:

```powershell
docker compose -f docker-compose.eth-btc-trend-compound-4h-v4-dryrun.yml run --rm freqtrade-eth-btc-trend-compound-4h-v4-dryrun backtesting `
  --config /freqtrade/user_data/config_eth_btc_trend_compound_4h_v4_dryrun.json `
  --strategy EthBtcTrendCompound4hV4 `
  --timerange 20200101-20260501 `
  --enable-protections
```

## Reproducibility Checklist

Before treating a run as evidence, record:

- repository commit SHA and strategy file path
- data source, exchange, pairs, timeframe, timerange, and whether the run uses futures or spot
- exact command used for data download, backtest, dry-run, or report generation
- config file path and any intentionally omitted secrets
- outputs reviewed: total return, max drawdown, trade count, profit factor, win rate, and failure notes
- public-safety check: no API keys, logs, SQLite databases, raw market data, or zipped backtest artifacts committed

This checklist makes results inspectable. It does not imply profitability.
## Evidence Standard

The public standard for this repository is:

- state the sample window
- show drawdown and failure modes
- keep rejected strategies documented
- avoid live-profit claims
- avoid uploading secrets, logs, raw data, or local databases

See `docs/results_summary.md` for the current public result summary.

## Next Steps

- Expand the reproducible data download guide with exact Freqtrade commands.
- Add a walk-forward validation summary with exact command lines.
- Publish the first GitHub release only after the public-safe file list is verified.
