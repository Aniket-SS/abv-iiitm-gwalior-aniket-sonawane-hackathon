from __future__ import annotations

import argparse

from src.ingestion.newsapi import fetch_newsapi
from src.ingestion.storage import write_jsonl

DEFAULT_QUERY = '("stock market" OR earnings OR inflation OR "Federal Reserve" OR sanctions OR downgrade OR bankruptcy)'


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch recent NewsAPI headlines/descriptions.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--days-back", type=int, default=7)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--output", default="data/processed/ingestion/newsapi_recent.jsonl")
    args = parser.parse_args()
    count = write_jsonl(fetch_newsapi(args.query, args.page_size, args.days_back), args.output)
    print(f"Wrote {count:,} NewsAPI documents to {args.output}")


if __name__ == "__main__":
    main()
