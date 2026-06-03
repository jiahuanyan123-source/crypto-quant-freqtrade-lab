# AI Daily Trader V1 使用说明

这个工具的目标不是直接实盘下单，而是每天生成一份“AI 交易计划”，再由机械风控规则审核。

它会做这些事：

1. 读取本地 ETH/BTC 的 15m、1h、4h 行情数据。
2. 计算趋势、涨跌幅、ATR 波动率、RSI、成交量、支撑压力等信息。
3. 把行情快照发给大模型，让它只输出 JSON 交易计划。
4. 风控模块审核这个计划。
5. 把行情、Prompt、AI 回答、风控结果写入 SQLite 数据库。

它现在不会真实下单。通过风控的计划只会写入 `paper_trades` 表，状态是 `planned`。

## 运行一次

在 `ft_userdata` 目录运行：

```powershell
.\user_data\tools\run_ai_daily_trader_v1.ps1
```

或者直接运行：

```powershell
python `
  .\user_data\tools\ai_daily_trader_v1.py `
  --config .\user_data\ai_daily_trader_v1_config.json `
  --once
```

## 配置 API Key

不要把 API Key 写进代码。打开 PowerShell 后临时设置：

```powershell
$env:AI_TRADER_API_KEY="你的key"
$env:AI_TRADER_BASE_URL="https://api.deepseek.com"
$env:AI_TRADER_MODEL="deepseek-reasoner"
```

如果没有设置 `AI_TRADER_API_KEY`，工具仍会运行，但会记录为 `no_trade`，用于检查数据和数据库是否正常。

## 不配置 API Key，直接用 Codex

当前聊天里的 Codex 不能被本地 Python 脚本自动调用，所以不用 API Key 的正确方式是“Codex 辅助模式”：

1. 脚本生成行情快照包。
2. Codex 在当前对话里读取快照并输出交易 JSON。
3. 脚本读取这个 JSON，执行风控审核并写入数据库。

生成 Codex 快照包：

```powershell
python `
  .\user_data\tools\ai_daily_trader_v1.py `
  --config .\user_data\ai_daily_trader_v1_config.json `
  --prepare-codex
```

快照包默认写到：

```text
user_data/ai_daily_trader_v1_codex_packet.json
```

把 Codex 给出的 JSON 保存为：

```text
user_data/ai_daily_trader_v1_codex_decision.json
```

然后运行风控和落库：

```powershell
python `
  .\user_data\tools\ai_daily_trader_v1.py `
  --config .\user_data\ai_daily_trader_v1_config.json `
  --decision-file .\user_data\ai_daily_trader_v1_codex_decision.json
```

## 数据库在哪里

默认数据库：

```text
user_data/ai_daily_trader_v1.sqlite
```

里面有两个核心表：

- `ai_decisions`：每一次 AI 决策和风控审核结果。
- `paper_trades`：通过风控的纸面交易计划。

## 风控闸门

AI 说可以交易还不够，必须通过这些硬规则：

- 信心分数至少 65。
- 必须有入场价、止损价、止盈价。
- 多单必须满足 `止损 < 入场 < 止盈`。
- 空单必须满足 `止盈 < 入场 < 止损`。
- 盈亏比至少 1.8。
- 止损距离不能太近，也不能太远。
- 仓位按账户风险自动反推，不使用固定数量开仓。
- 默认不做强逆势单。

## 下一步

第一阶段先每天记录，不实盘。等积累 30-60 天记录后，再统计：

- AI 选择交易的频率。
- 通过风控的比例。
- 纸面交易的胜率和盈亏比。
- AI 的理由是否前后一致。
- 它是否真的比机械策略更有 edge。
