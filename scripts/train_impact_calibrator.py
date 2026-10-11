"""Train a time-split impact calibrator from Phase 5 event-study observations."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import csv
import joblib
from src.common.config import resolve_path
from src.market.learned_impact import load_event_rows, fit_evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", default="data/processed/phase5/impact_event_study.csv")
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--output-dir", default="data/processed/phase5")
    args = parser.parse_args()
    events_path = resolve_path(args.events)
    output_dir = resolve_path(args.output_dir)
    rows = load_event_rows(events_path, args.horizon)
    if not rows:
        raise SystemExit(f"No usable rows for {args.horizon}-day horizon in {events_path}. Run scripts.calibrate_impact first.")
    metrics, model, holdout = fit_evaluate(rows)
    metrics["horizon_trading_days"] = args.horizon
    metrics["source_event_file"] = str(args.events)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "learned_impact_model.joblib"
    metrics_path = output_dir / "learned_impact_metrics.json"
    holdout_path = output_dir / "learned_impact_holdout.csv"
    joblib.dump(model, model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if holdout:
        with holdout_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(holdout[0]))
            writer.writeheader()
            writer.writerows(holdout)
    print(f"Input observations: {len(rows):,}")
    print(f"Unique ticker/date observations: {metrics['observations_after_same_ticker_date_aggregation']:,}")
    print(f"Baseline holdout Spearman: {metrics['baseline_impact_spearman_holdout']}")
    print(f"Predicted magnitude holdout Spearman: {metrics['predicted_magnitude_spearman_holdout']}")
    print(f"Holdout MAE: {metrics['holdout_mae_percentage_points']} percentage points")
    print(f"Model: {model_path}")
    print(f"Metrics: {metrics_path}")
    print(f"Holdout rows: {holdout_path}")
    print("Do not deploy the learned score as an improvement unless holdout metrics beat the baseline and band ordering is reviewed.")

if __name__ == "__main__":
    main()
