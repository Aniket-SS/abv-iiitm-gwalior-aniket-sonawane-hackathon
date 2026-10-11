from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.common.schemas import Signal
from src.signals.store import SignalStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and import Signal JSONL into SQLite.")
    parser.add_argument("input", type=Path, help="Path to Signal JSONL file")
    parser.add_argument("--db", type=Path, default=None, help="SQLite path (defaults to config/settings.yaml)")
    parser.add_argument("--batch-size", type=int, default=2000, help="Number of signals per transaction")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if not args.input.is_file():
        parser.error(f"Input file does not exist: {args.input}")

    store = SignalStore(args.db)
    batch: list[Signal] = []
    parsed = 0
    with args.input.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                batch.append(Signal.model_validate(json.loads(line)))
            except Exception as exc:
                print(f"Invalid signal at line {line_no}: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
            if len(batch) >= args.batch_size:
                store.upsert_many(batch)
                parsed += len(batch)
                batch.clear()
                print(f"Imported/updated {parsed:,} signals...", flush=True)
    if batch:
        store.upsert_many(batch)
        parsed += len(batch)
    print(f"Validated and imported/updated: {parsed:,}")
    print(f"Signals currently in database: {store.count():,}")
    print(f"Database: {store.db_path}")


if __name__ == "__main__":
    main()
