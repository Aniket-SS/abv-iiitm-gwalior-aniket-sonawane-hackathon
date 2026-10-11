"""Run Phase 5 exploratory impact calibration against historical prices.

Example:
  python -m scripts.calibrate_impact --prices data/raw/prices/prices_daily.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from src.common.config import resolve_path
from src.market.calibration import event_study, load_prices, load_signals_from_sqlite, summarize_calibration


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", default="data/raw/prices/prices_daily.csv")
    parser.add_argument("--db", default="data/processed/signals.db")
    parser.add_argument("--output-dir", default="data/processed/phase5")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--horizons", type=int, nargs="+", default=[1, 3, 5])
    parser.add_argument("--summary-horizon", type=int, default=3)
    args = parser.parse_args()
    if args.summary_horizon not in args.horizons:
        parser.error("--summary-horizon must also appear in --horizons")

    prices_path = resolve_path(args.prices)
    db_path = resolve_path(args.db)
    out_dir = resolve_path(args.output_dir)
    prices = load_prices(prices_path)
    if args.benchmark.upper() not in prices:
        raise SystemExit(f"Benchmark {args.benchmark.upper()} is missing from {prices_path}. Fetch prices including the benchmark first.")
    signals = load_signals_from_sqlite(db_path)
    rows = event_study(signals, prices, benchmark=args.benchmark.upper(), horizons=tuple(args.horizons))
    if not rows:
        raise SystemExit("No signals could be matched to the supplied price data. Check ticker symbols and date coverage.")

    out_dir.mkdir(parents=True, exist_ok=True)
    event_path = out_dir / "impact_event_study.csv"
    summary_path = out_dir / "impact_calibration_summary.json"
    report_path = resolve_path("docs/notes/impact_calibration.md")
    write_csv(event_path, rows)
    summary = summarize_calibration(rows, args.summary_horizon)
    summary.update({
        "signals_in_database": len(signals),
        "signals_matched_to_prices": len(rows),
        "price_tickers": sorted(prices),
        "price_date_min": min(day for series in prices.values() for day in series).isoformat(),
        "price_date_max": max(day for series in prices.values() for day in series).isoformat(),
        "benchmark": args.benchmark.upper(),
        "source_price_file": str(args.prices),
        "source_database": str(args.db),
        "generated_on": date.today().isoformat(),
    })
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    band_lines = ["| Impact band | Signals | Mean absolute abnormal return (%) | Median absolute abnormal return (%) |", "|---|---:|---:|---:|"]
    for band in summary["bands"]:
        mean = "—" if band["mean_abs_abnormal_return_pct"] is None else f"{band['mean_abs_abnormal_return_pct']:.4f}"
        median = "—" if band["median_abs_abnormal_return_pct"] is None else f"{band['median_abs_abnormal_return_pct']:.4f}"
        band_lines.append(f"| {band['impact_band']} | {band['count']} | {mean} | {median} |")
    report = f"""# Phase 5 — Impact calibration report

## Run metadata

- Generated: {summary['generated_on']}
- Signals in SQLite: {len(signals):,}
- Signals with a matched starting price date: {len(rows):,}
- Signals with a complete {args.summary_horizon}-day outcome: {summary['matched_signals']:,}
- Price date range: {summary['price_date_min']} to {summary['price_date_max']}
- Price tickers: {', '.join(summary['price_tickers'])}
- Benchmark: {summary['benchmark']}
- Evaluation horizon: {args.summary_horizon} trading days

## Results

- Spearman correlation between existing impact score and absolute abnormal return: {summary['impact_vs_abs_abnormal_return_spearman']}
- Mean absolute abnormal return: {summary.get('mean_abs_abnormal_return_pct')}

{chr(10).join(band_lines)}

## Interpretation and limitations

This is an exploratory event-study diagnostic, not proof of causality or predictive performance. A positive correlation means higher existing impact scores tended to coincide with larger absolute abnormal returns in this matched sample; it does not establish that the signal predicted those returns. Daily prices cannot resolve the intraday publication time, event observations can overlap, signals can be duplicated across sources, and historical price coverage may exclude tickers or dates. Market-scope signals use the benchmark's own return as the outcome. Company-scope abnormal return is ticker return minus benchmark return. Impact scores are not modified by this script.

## Files

- Event-level observations: `data/processed/phase5/impact_event_study.csv`
- Machine-readable summary: `data/processed/phase5/impact_calibration_summary.json`
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"Signals in database: {len(signals):,}")
    print(f"Signals with a matched starting price date: {len(rows):,}")
    print(f"Signals with a complete {args.summary_horizon}-day outcome: {summary['matched_signals']:,}")
    print(f"Benchmark: {args.benchmark.upper()}; summary horizon: {args.summary_horizon} trading days")
    print(f"Spearman(impact, absolute abnormal return): {summary['impact_vs_abs_abnormal_return_spearman']}")
    print(f"Event study: {event_path}")
    print(f"Summary: {summary_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
