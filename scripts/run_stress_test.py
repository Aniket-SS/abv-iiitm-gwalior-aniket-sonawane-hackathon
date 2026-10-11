from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from src.modules.stress_test.engine import load_portfolio, load_scenarios, run_stress_test

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an event-driven stress test on the synthetic wholesale portfolio.")
    parser.add_argument("--db", default=str(ROOT / "data/processed/signals.db"))
    parser.add_argument("--portfolio", default=str(ROOT / "data/synthetic/wholesale_portfolio.csv"))
    parser.add_argument("--scenarios", default=str(ROOT / "config/stress_scenarios.yaml"))
    parser.add_argument("--output", default=str(ROOT / "data/processed/phase7/latest_stress_test.json"))
    parser.add_argument("--threshold", type=float, default=7.0)
    parser.add_argument("--signal-id", default=None)
    parser.add_argument("--scope", choices=["all", "company", "event", "market"], default="all")
    parser.add_argument("--ticker", default=None, help="Optional ticker filter; leave unset for market/event signals without a company ticker.")
    parser.add_argument("--event-type", default=None, help="Optional event type filter, e.g. geopolitical or credit_event.")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"Signal database not found: {db_path}. Run the signal pipeline first.")
    where = ["impact >= ?"]
    params: list[object] = [args.threshold]
    if args.signal_id:
        where.append("signal_id = ?")
        params.append(args.signal_id)
    if args.scope != "all":
        where.append("LOWER(COALESCE(scope, 'company')) = ?")
        params.append(args.scope)
    if args.ticker:
        where.append("UPPER(COALESCE(ticker, '')) = ?")
        params.append(args.ticker.upper())
    if args.event_type:
        where.append("LOWER(COALESCE(event_type, 'other')) = ?")
        params.append(args.event_type.lower())

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            f"SELECT * FROM signals WHERE {' AND '.join(where)} ORDER BY timestamp DESC LIMIT 1",
            params,
        ).fetchone()
    if row is None:
        raise SystemExit("No signal matched these filters. Lower --threshold or change --scope/--event-type/--ticker.")

    signal = dict(row)
    portfolio = load_portfolio(args.portfolio)
    scenarios = load_scenarios(args.scenarios)
    result = run_stress_test(signal, portfolio, scenarios, impact_threshold=args.threshold)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str, allow_nan=False))
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
