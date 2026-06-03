import argparse
import csv
import json
import math
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


V5_CONFIG = "/freqtrade/user_data/config_moonshot_adaptive_regime_5m_v5_dryrun.json"
V6_CONFIG = "/freqtrade/user_data/config_moonshot_adaptive_ml_filter_5m_v6_dryrun.json"
V5_STRATEGY = "MoonshotAdaptiveRegime5mV5"
V6_STRATEGY = "MoonshotAdaptiveMLFilter5mV6"


@dataclass
class FoldResult:
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    strategy: str
    profit_pct: float
    drawdown_pct: float
    trades: int
    profit_factor: float
    winrate: float
    best_pair: str
    worst_pair: str
    result_zip: str


def run_command(project_root: Path, label: str, command: list[str]) -> None:
    print(f"==> {label}", flush=True)
    completed = subprocess.run(
        command,
        cwd=project_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        print(completed.stdout[-6000:])
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")


def parse_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc).date()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if isinstance(parsed, datetime):
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(value)


def ymd(value: datetime) -> str:
    return value.strftime("%Y%m%d")


def iso_z(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT00:00:00Z")


def read_latest_result(project_root: Path, strategy_name: str) -> tuple[dict, str]:
    result_dir = project_root / "user_data" / "backtest_results"
    last_path = result_dir / ".last_result.json"
    latest = json.loads(last_path.read_text(encoding="utf-8"))
    zip_name = latest["latest_backtest"]
    zip_path = result_dir / zip_name

    with zipfile.ZipFile(zip_path) as archive:
        json_name = [
            name
            for name in archive.namelist()
            if name.endswith(".json") and not name.endswith("_config.json")
        ][0]
        payload = json.loads(archive.read(json_name))

    strategy = payload["strategy"][strategy_name]
    return strategy, zip_name


def percent_metric(strategy: dict, percent_key: str, ratio_key: str) -> float:
    value = strategy.get(percent_key)
    if value is not None:
        return float(value)
    return float(strategy.get(ratio_key, 0.0)) * 100.0


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        value = float(value)
        if math.isfinite(value):
            return value
    except (TypeError, ValueError):
        pass
    return default


def summarize_strategy(
    project_root: Path,
    fold: int,
    train_start: datetime,
    train_end: datetime,
    test_start: datetime,
    test_end: datetime,
    strategy_name: str,
) -> FoldResult:
    strategy, zip_name = read_latest_result(project_root, strategy_name)

    pairs = [
        pair
        for pair in strategy.get("results_per_pair", [])
        if pair.get("key") != "TOTAL" and int(pair.get("trades", 0) or 0) > 0
    ]
    pairs_sorted = sorted(pairs, key=lambda item: safe_float(item.get("profit_total_pct")))
    worst_pair = pairs_sorted[0]["key"] if pairs_sorted else ""
    best_pair = pairs_sorted[-1]["key"] if pairs_sorted else ""

    trades = int(strategy.get("total_trades", 0) or 0)
    wins = int(strategy.get("wins", 0) or 0)
    winrate = wins / trades * 100.0 if trades else 0.0

    return FoldResult(
        fold=fold,
        train_start=train_start.strftime("%Y-%m-%d"),
        train_end=train_end.strftime("%Y-%m-%d"),
        test_start=test_start.strftime("%Y-%m-%d"),
        test_end=test_end.strftime("%Y-%m-%d"),
        strategy=strategy_name,
        profit_pct=percent_metric(strategy, "profit_total_pct", "profit_total"),
        drawdown_pct=safe_float(strategy.get("max_drawdown_account")) * 100.0,
        trades=trades,
        profit_factor=safe_float(strategy.get("profit_factor")),
        winrate=winrate,
        best_pair=best_pair,
        worst_pair=worst_pair,
        result_zip=zip_name,
    )


def backtest(
    project_root: Path,
    config_path: str,
    strategy_name: str,
    timerange: str,
) -> None:
    run_command(
        project_root,
        f"Backtest {strategy_name} {timerange}",
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "freqtrade",
            "backtesting",
            "--config",
            config_path,
            "--strategy",
            strategy_name,
            "--timerange",
            timerange,
            "--timeframe",
            "5m",
            "--enable-protections",
            "--cache",
            "none",
        ],
    )


def train_v6(
    project_root: Path,
    train_days: int,
    train_end: datetime,
    horizon_candles: int,
    take_profit: float,
    stop_loss: float,
) -> None:
    run_command(
        project_root,
        f"Train V6 through {train_end:%Y-%m-%d}",
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "freqtrade",
            "/freqtrade/user_data/tools/train_v6_ml_filter.py",
            "--train-days",
            str(train_days),
            "--end-date",
            iso_z(train_end),
            "--horizon-candles",
            str(horizon_candles),
            "--take-profit",
            str(take_profit),
            "--stop-loss",
            str(stop_loss),
        ],
    )


def retrain_latest_v6(
    project_root: Path,
    train_days: int,
    horizon_candles: int,
    take_profit: float,
    stop_loss: float,
) -> None:
    run_command(
        project_root,
        "Restore latest V6 research model",
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "freqtrade",
            "/freqtrade/user_data/tools/train_v6_ml_filter.py",
            "--train-days",
            str(train_days),
            "--horizon-candles",
            str(horizon_candles),
            "--take-profit",
            str(take_profit),
            "--stop-loss",
            str(stop_loss),
        ],
    )


def write_csv(path: Path, rows: list[FoldResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FoldResult.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def aggregate(rows: list[FoldResult], strategy: str) -> dict:
    selected = [row for row in rows if row.strategy == strategy]
    if not selected:
        return {}
    return {
        "strategy": strategy,
        "folds": len(selected),
        "sum_profit_pct": sum(row.profit_pct for row in selected),
        "average_profit_pct": sum(row.profit_pct for row in selected) / len(selected),
        "positive_folds": sum(1 for row in selected if row.profit_pct > 0),
        "total_trades": sum(row.trades for row in selected),
        "worst_fold_profit_pct": min(row.profit_pct for row in selected),
        "worst_drawdown_pct": max(row.drawdown_pct for row in selected),
    }


def verdict(rows: list[FoldResult], folds: int, min_total_trades: int) -> tuple[str, list[str]]:
    v5 = aggregate(rows, V5_STRATEGY)
    v6 = aggregate(rows, V6_STRATEGY)
    paired = {}
    for row in rows:
        paired.setdefault(row.fold, {})[row.strategy] = row

    v6_beats_v5 = sum(
        1
        for pair in paired.values()
        if V5_STRATEGY in pair
        and V6_STRATEGY in pair
        and pair[V6_STRATEGY].profit_pct > pair[V5_STRATEGY].profit_pct
    )

    required_consistency = math.ceil(folds * 0.55)
    failed = []
    if v6["sum_profit_pct"] <= v5["sum_profit_pct"]:
        failed.append("V6 total sample-out profit is not better than V5.")
    if v6["positive_folds"] < required_consistency:
        failed.append(f"V6 positive folds {v6['positive_folds']} < {required_consistency}.")
    if v6_beats_v5 < required_consistency:
        failed.append(f"V6 beats V5 in {v6_beats_v5} folds < {required_consistency}.")
    if v6["total_trades"] < min_total_trades:
        failed.append(f"V6 total trades {v6['total_trades']} < {min_total_trades}.")
    if v6["worst_drawdown_pct"] > 15.0:
        failed.append(f"V6 worst drawdown {v6['worst_drawdown_pct']:.2f}% > 15%.")
    if v6["worst_fold_profit_pct"] < -10.0:
        failed.append(f"V6 worst fold profit {v6['worst_fold_profit_pct']:.2f}% < -10%.")

    return ("PASS" if not failed else "FAIL"), failed


def write_report(path: Path, rows: list[FoldResult], folds: int, min_total_trades: int) -> None:
    v5 = aggregate(rows, V5_STRATEGY)
    v6 = aggregate(rows, V6_STRATEGY)
    status, failed = verdict(rows, folds, min_total_trades)

    paired = {}
    for row in rows:
        paired.setdefault(row.fold, {})[row.strategy] = row
    v6_beats_v5 = sum(
        1
        for pair in paired.values()
        if V5_STRATEGY in pair
        and V6_STRATEGY in pair
        and pair[V6_STRATEGY].profit_pct > pair[V5_STRATEGY].profit_pct
    )

    lines = [
        "# Walk-Forward Anti-Overfit Validation",
        "",
        f"- Status: {status}",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Folds: {folds}",
        "- Rule: each V6 fold trains only on data before the fold's test window.",
        "- Rule: V6 must beat V5 out-of-sample, not just inside the fitted period.",
        "",
        "## Aggregate",
        "",
        "| Strategy | Sum Profit % | Avg Profit % | Positive Folds | Total Trades | Worst Fold % | Worst DD % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in [v5, v6]:
        lines.append(
            f"| {item['strategy']} | {item['sum_profit_pct']:.2f} | {item['average_profit_pct']:.2f} | "
            f"{item['positive_folds']}/{item['folds']} | {item['total_trades']} | "
            f"{item['worst_fold_profit_pct']:.2f} | {item['worst_drawdown_pct']:.2f} |"
        )

    lines += [
        "",
        f"- V6 beat V5 in {v6_beats_v5}/{folds} folds.",
        "",
        "## Fold Details",
        "",
        "| Fold | Test Window | V5 Profit % | V5 Trades | V6 Profit % | V6 Trades | V6 - V5 |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for fold in sorted(paired):
        v5_row = paired[fold].get(V5_STRATEGY)
        v6_row = paired[fold].get(V6_STRATEGY)
        diff = (v6_row.profit_pct - v5_row.profit_pct) if v5_row and v6_row else 0.0
        lines.append(
            f"| {fold} | {v5_row.test_start} to {v5_row.test_end} | "
            f"{v5_row.profit_pct:.2f} | {v5_row.trades} | "
            f"{v6_row.profit_pct:.2f} | {v6_row.trades} | {diff:.2f} |"
        )

    lines += ["", "## Failed Rules", ""]
    if failed:
        lines.extend(f"- {item}" for item in failed)
    else:
        lines.append("- None.")

    lines += [
        "",
        "## Research Decision",
        "",
    ]
    if status == "PASS":
        lines.append("- V6 passed this sample-out validation run. It may enter dry-run observation, but still not live trading.")
    else:
        lines.append("- V6 failed this sample-out validation run. Keep it as a research candidate and do not replace V5.")

    lines += [
        "- Do not accept an in-sample result unless this report also passes.",
        "- Do not use Hyperopt or ML results from the same window as proof of profitability.",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--folds", type=int, default=8)
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--test-days", type=int, default=14)
    parser.add_argument("--horizon-candles", type=int, default=288)
    parser.add_argument("--take-profit", type=float, default=0.040)
    parser.add_argument("--stop-loss", type=float, default=0.012)
    parser.add_argument("--min-total-trades", type=int, default=8)
    parser.add_argument("--skip-latest-retrain", action="store_true")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else script_path.parents[2]
    end_date = parse_date(args.end_date) if args.end_date else (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    rows: list[FoldResult] = []
    first_test_start = end_date - timedelta(days=args.folds * args.test_days)

    for index in range(args.folds):
        fold = index + 1
        test_start = first_test_start + timedelta(days=index * args.test_days)
        test_end = test_start + timedelta(days=args.test_days)
        train_end = test_start
        train_start = train_end - timedelta(days=args.train_days)
        timerange = f"{ymd(test_start)}-{ymd(test_end)}"

        print(f"\n### Fold {fold}/{args.folds}: train <= {train_end:%Y-%m-%d}, test {timerange}", flush=True)

        backtest(project_root, V5_CONFIG, V5_STRATEGY, timerange)
        rows.append(summarize_strategy(project_root, fold, train_start, train_end, test_start, test_end, V5_STRATEGY))

        train_v6(project_root, args.train_days, train_end, args.horizon_candles, args.take_profit, args.stop_loss)
        backtest(project_root, V6_CONFIG, V6_STRATEGY, timerange)
        rows.append(summarize_strategy(project_root, fold, train_start, train_end, test_start, test_end, V6_STRATEGY))

        v5_row = rows[-2]
        v6_row = rows[-1]
        print(
            f"Fold {fold} summary: V5 {v5_row.profit_pct:.2f}%/{v5_row.trades} trades, "
            f"V6 {v6_row.profit_pct:.2f}%/{v6_row.trades} trades",
            flush=True,
        )

    if not args.skip_latest_retrain:
        retrain_latest_v6(project_root, args.train_days, args.horizon_candles, args.take_profit, args.stop_loss)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = project_root / "user_data" / "reports"
    csv_path = report_dir / f"walkforward_validation_{stamp}.csv"
    report_path = report_dir / f"walkforward_validation_{stamp}.md"
    write_csv(csv_path, rows)
    write_report(report_path, rows, args.folds, args.min_total_trades)

    status, failed = verdict(rows, args.folds, args.min_total_trades)
    print(f"\nWalk-forward report: {report_path}")
    print(f"Walk-forward csv: {csv_path}")
    print(f"Walk-forward status: {status}")
    if failed:
        for item in failed:
            print(f"- {item}")
        sys.exit(2)


if __name__ == "__main__":
    main()
