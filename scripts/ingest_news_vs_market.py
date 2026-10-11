from __future__ import annotations

import argparse
from src.ingestion.news_vs_market import read_news_vs_market
from src.ingestion.storage import write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize news_vs_market_2020 raw articles into Document JSONL.")
    parser.add_argument("--input", default="data/raw/news_vs_market_2020/news_sentiment_raw.csv")
    parser.add_argument("--output", default="data/processed/ingestion/news_vs_market.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    count = write_jsonl(read_news_vs_market(args.input, limit=args.limit), args.output)
    print(f"Wrote {count:,} normalized news_vs_market documents to {args.output}")


if __name__ == "__main__":
    main()
