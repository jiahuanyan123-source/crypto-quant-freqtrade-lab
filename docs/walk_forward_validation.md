# Walk-Forward Validation Plan

This document defines the public walk-forward validation protocol for `EthBtcTrendCompound4hV4`.

It does not claim profitability. A window is useful evidence only after the exact command, timerange, output metrics, and failure notes are recorded.

## Scope

- Strategy: `EthBtcTrendCompound4hV4`
- Config: `ft_userdata/user_data/config_eth_btc_trend_compound_4h_v4_dryrun.json`
- Compose file: `ft_userdata/docker-compose.eth-btc-trend-compound-4h-v4-dryrun.yml`
- Timeframe: 4h
- Data location: `ft_userdata/user_data/data/` (ignored by Git)
- Run directory: `ft_userdata`

Before running these commands, follow the README `Data Download Guide`.

## Window Commands

### Window A: 2020-01-01 to 2021-12-31

```powershell
cd ft_userdata
docker compose -f docker-compose.eth-btc-trend-compound-4h-v4-dryrun.yml run --rm freqtrade-eth-btc-trend-compound-4h-v4-dryrun backtesting `
  --config /freqtrade/user_data/config_eth_btc_trend_compound_4h_v4_dryrun.json `
  --strategy EthBtcTrendCompound4hV4 `
  --timerange 20200101-20211231 `
  --enable-protections
```

### Window B: 2022-01-01 to 2023-12-31

```powershell
cd ft_userdata
docker compose -f docker-compose.eth-btc-trend-compound-4h-v4-dryrun.yml run --rm freqtrade-eth-btc-trend-compound-4h-v4-dryrun backtesting `
  --config /freqtrade/user_data/config_eth_btc_trend_compound_4h_v4_dryrun.json `
  --strategy EthBtcTrendCompound4hV4 `
  --timerange 20220101-20231231 `
  --enable-protections
```

### Window C: 2024-01-01 to 2026-05-01

```powershell
cd ft_userdata
docker compose -f docker-compose.eth-btc-trend-compound-4h-v4-dryrun.yml run --rm freqtrade-eth-btc-trend-compound-4h-v4-dryrun backtesting `
  --config /freqtrade/user_data/config_eth_btc_trend_compound_4h_v4_dryrun.json `
  --strategy EthBtcTrendCompound4hV4 `
  --timerange 20240101-20260501 `
  --enable-protections
```

## Result Table Template

Fill this table only after the commands have been run from a clean public commit.

| Window | Timerange | Total return | Max drawdown | Trades | Profit factor | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A | 20200101-20211231 | pending | pending | pending | pending | Run not yet recorded in public repo. |
| B | 20220101-20231231 | pending | pending | pending | pending | Run not yet recorded in public repo. |
| C | 20240101-20260501 | pending | pending | pending | pending | Run not yet recorded in public repo. |

## Acceptance Rules

- Record the repository commit SHA before running commands.
- Record exact timerange and config path for each run.
- Record total return, maximum drawdown, trade count, profit factor, and notable failure modes.
- Do not publish raw data, logs, SQLite files, or zipped backtest artifacts.
- Do not describe any window as proof of future returns.