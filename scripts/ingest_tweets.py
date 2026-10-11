from __future__ import annotations

import argparse
from src.ingestion.historical_tweets import read_tweets
from src.ingestion.storage import write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize historical stock tweets into canonical Document JSONL.")
    parser.add_argument("--input", default="data/raw/stock_tweets/stock_tweets.csv")
    parser.add_argument("--output", default="data/processed/ingestion/stock_tweets.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="Optional small limit for a quick smoke test")
    args = parser.parse_args()
    count = write_jsonl(read_tweets(args.input, limit=args.limit), args.output)
    print(f"Wrote {count:,} normalized tweet documents to {args.output}")


if __name__ == "__main__":
    main()
