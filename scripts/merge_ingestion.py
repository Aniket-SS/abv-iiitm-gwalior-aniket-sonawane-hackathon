from __future__ import annotations

import argparse
from src.ingestion.storage import merge_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge normalized source JSONL files and deduplicate by URL/document ID.")
    parser.add_argument("inputs", nargs="+", help="Input JSONL files")
    parser.add_argument("--output", default="data/processed/ingestion/documents.jsonl")
    args = parser.parse_args()
    count = merge_jsonl(args.inputs, args.output)
    print(f"Wrote {count:,} unique documents to {args.output}")


if __name__ == "__main__":
    main()
