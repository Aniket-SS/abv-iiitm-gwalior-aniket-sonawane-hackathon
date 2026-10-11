from __future__ import annotations

import argparse

from src.ingestion.gdelt_api import fetch_gdelt
from src.ingestion.storage import write_jsonl

DEFAULT_QUERY = '("stock market" OR earnings OR inflation OR "Federal Reserve" OR sanctions OR downgrade OR bankruptcy)'


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch recent article metadata from the GDELT DOC API.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--timespan", default="1week", help="GDELT recent window, e.g. 1day or 1week")
    parser.add_argument("--max-records", type=int, default=100)
    parser.add_argument("--output", default="data/processed/ingestion/gdelt_recent.jsonl")
    args = parser.parse_args()
    count = write_jsonl(fetch_gdelt(args.query, args.timespan, args.max_records), args.output)
    print(f"Wrote {count:,} GDELT documents to {args.output}")


if __name__ == "__main__":
    main()
