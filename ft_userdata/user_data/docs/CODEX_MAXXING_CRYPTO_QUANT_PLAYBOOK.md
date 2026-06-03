# Codex-Maxxer Crypto Quant Playbook

This project uses Codex as a long-running crypto quant research operator, not as a one-off chat bot.

## Current Mission

Build and validate crypto trading systems for small-capital, high-upside futures trading while avoiding untested discretionary gambling.

## Operating Principles

1. Durable thread
   - Keep this thread as the main project room.
   - Before major work, inspect current files, Docker status, data freshness, and databases.
   - Do not rely only on memory when local state can be checked.

2. Explicit memory
   - Important conclusions should be written into project files, not left only in chat.
   - Strategy status, backtest results, open questions, and rejected directions should be preserved.

3. Verification before confidence
   - Any Freqtrade strategy must be validated with official backtests before being treated as usable.
   - Any Codex subjective trade idea must be logged as paper-only until forward data proves edge.
   - No strategy is promoted because it feels smart.

4. Two-track system
   - Freqtrade mechanical strategies are the execution track.
   - Codex daily trading meetings are the research and review track.
   - Codex may inspire strategy rules, but Freqtrade must verify them.

5. Risk truth
   - High leverage is allowed only inside a separated sprint strategy.
   - Sprint strategies must use hard stoploss, max margin fraction, max leverage, and cooldown rules.
   - Never describe 25% margin at 10x as low risk; it is 2.5x account exposure.

6. Anti-overfitting discipline
   - Fixed sample splits should be declared before optimization.
   - Recent-data tuning must be labeled as regime adaptation, not proof of long-term edge.
   - Any new strategy needs full-period, recent-period, and stress-period checks.

## Current Project State

Main mechanical strategy:

- `EthBtcTrendCompound4hV4.py`
- ETH perpetual long-only trend strategy.
- Official full backtest from 2020-04-10 to 2026-05-01 showed +1893.27% with 17.90% max drawdown.
- This is a low-frequency trend strategy, not a high-leverage sprint strategy.

Codex research system:

- `ai_daily_trader_v1.py`
- Generates ETH/BTC market snapshots and records Codex trading decisions.
- Paper-only; does not place real orders.

High-risk sprint research:

- `MomentumSprint1hV1.py`
- `MomentumSprint1hV2.py`
- Intended high-risk, high-upside long/short futures sprint strategy.
- Status: research only, not promoted to dry-run.
- V1 official backtest from 2025-01-01 to 2026-06-03 lost 46.90%, with 48.93% max drawdown.
- V2 reduced drawdown sharply but still lost 7.28% from 2025-01-01 to 2026-06-03; recent 2026-04-01 to 2026-06-03 result was -0.10%.
- Conclusion: the current 1h high-leverage breakout implementation does not yet show positive expectancy. Do not run it as a trading bot until a later version passes full-period and recent-period tests.

4h regime trend V5 research:

- `EthBtcRegimeTrend4hV5.py`
- Purpose: make V4 more active by adding confirmed short-side trading and relaxed long continuation entries.
- Status: research only, not promoted to dry-run.
- Full backtest from 2020-04-10 to 2026-06-03 showed +208.10% with 25.11% max drawdown, far worse than V4's previously recorded +1893.27% with 17.90% max drawdown.
- Recent 2025-01-01 to 2026-06-03 result was +27.47%, while V4 on the same period showed +67.09%.
- Conclusion: V5 increases trades but degrades quality. The short side is negative and should not be promoted.

Multi-asset 4h regime trend V1 research:

- `MultiAssetRegimeTrend4hV1.py`
- Purpose: test whether V4's 4h risk-on trend edge generalizes from ETH to a broader OKX futures whitelist.
- Status: research only, not promoted to dry-run.
- On 2026-06-03, 4h futures data was refreshed for BTC, ETH, SOL, XRP, DOGE, BNB, LINK, AVAX, NEAR, ADA, SUI, PEPE, WIF, BONK, and FLOKI.
- Main recent backtest from 2025-01-01 to 2026-06-03 showed +6.83% with 18.24% max drawdown, 28 trades, 57.1% win rate, and 1.22 profit factor.
- V4 rerun on the same period showed +67.09% with 17.90% max drawdown, 6 trades, 50.0% win rate, and 2.22 profit factor.
- Recent 2026-04-01 to 2026-06-03 result was +5.52% with 1.76% max drawdown, but this sample is too short to promote.
- Conclusion: broad multi-asset rotation dilutes V4's edge. Do not start this candidate as a bot unless a later version proves stricter pair selection or relative-strength ranking works.

Moonshot watchlist:

- `moonshot_watchlist_v1.py`
- Scans local OKX futures 1h candles and creates `moonshot_watchlist_latest.md/json`.
- Status: usable as an opportunity radar only; it does not place orders and does not prove a trade is profitable.

## Default Workflow For Future Strategy Work

1. Inspect current state.
2. State the edge hypothesis.
3. Implement the smallest testable Freqtrade strategy.
4. Run official backtests.
5. Compare against V4 and simple baselines.
6. Reject, revise, or promote to dry-run.
7. Write the outcome into project memory.

## Default Workflow For Daily Trading Meeting

1. Update data.
2. Generate Codex packet.
3. Codex returns one JSON decision.
4. Mechanical risk gate accepts or rejects it.
5. Save to SQLite.
6. Never treat one decision as proof of edge.

## Autonomous Improvement Loop

Codex-maxxing does not mean blindly optimizing until a backtest looks good. For this project it means running a disciplined loop:

1. Observe
   - Check Docker state, strategy files, data freshness, dry-run databases, and decision logs.

2. Diagnose
   - Identify whether the current bottleneck is missing data, bad execution assumptions, weak edge, overfitting, or no recent market opportunity.

3. Propose
   - Produce concrete next actions, such as rerun a backtest, refresh data, build a new strategy candidate, or reject an idea.

4. Verify
   - Any code change must be tested with official Freqtrade backtests before promotion.

5. Record
   - Important results and rejected paths should be written into project memory, not left only in chat.

6. Escalate Carefully
   - Moving from research to dry-run, and from dry-run to real capital, requires evidence. A beautiful backtest alone is not enough.

## Public Maintenance Loop

The project can use scheduled or manual healthchecks to inspect project state and recommend next actions. These checks should not mutate trading logic without a user-requested development cycle.

Specific local automation ids and private handoff files are intentionally kept out of the public baseline.
