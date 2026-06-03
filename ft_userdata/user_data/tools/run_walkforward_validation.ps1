param(
    [string]$ProjectRoot = "",
    [int]$Folds = 6,
    [int]$TrainDays = 90,
    [int]$TestDays = 14,
    [string]$EndDate = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
}

Push-Location $ProjectRoot
try {
    $arguments = @(
        ".\user_data\tools\run_walkforward_validation.py",
        "--folds", "$Folds",
        "--train-days", "$TrainDays",
        "--test-days", "$TestDays"
    )
    if ($EndDate) {
        $arguments += @("--end-date", $EndDate)
    }

    python @arguments

    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
