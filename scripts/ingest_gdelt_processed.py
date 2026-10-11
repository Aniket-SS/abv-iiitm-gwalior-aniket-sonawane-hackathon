
from __future__ import annotations

import argparse

from src.ingestion.gdelt_processed import load_processed_gdelt
from src.ingestion.storage import write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize existing processed GDELT JSONL files."
    )
    parser.add_argument(
        "--output",
        default="data/processed/ingestion/gdelt_documents.jsonl",
    )
    args = parser.parse_args()

    documents = load_processed_gdelt()
    count = write_jsonl(documents, args.output)

    print(f"Normalized {count} GDELT documents to {args.output}")


if __name__ == "__main__":
    main()
