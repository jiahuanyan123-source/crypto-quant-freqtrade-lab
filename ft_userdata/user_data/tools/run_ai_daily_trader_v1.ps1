$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$config = Join-Path $repoRoot "user_data\ai_daily_trader_v1_config.json"
$script = Join-Path $repoRoot "user_data\tools\ai_daily_trader_v1.py"

$python = if ($env:CODEX_BUNDLED_PYTHON) { $env:CODEX_BUNDLED_PYTHON } else { "python" }
& $python $script --config $config --once
