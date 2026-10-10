from __future__ import annotations

import argparse
from pathlib import Path

from src.ingestion.gdelt import read_tabular_file, write_jsonl


def find_data_file(root: Path, kind: str) -> Path:
    patterns = {"export": "*.export.CSV", "mentions": "*.mentions.CSV", "gkg": "*.gkg.csv"}
    matches = sorted(root.rglob(patterns[kind]))
    if not matches:
        raise FileNotFoundError(f"No extracted {kind} file found under {root}")
    return matches[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", default="data/raw/gdelt/extracted")
    parser.add_argument("--output-root", default="data/processed/gdelt")
    args = parser.parse_args()

    input_root, output_root = Path(args.input_root), Path(args.output_root)
    if not input_root.exists():
        raise FileNotFoundError(f"Input folder does not exist: {input_root}")

    for kind in ("export", "mentions", "gkg"):
        source_path = find_data_file(input_root, kind)
        output_path = output_root / f"{kind}_latest.jsonl"
        count = write_jsonl(read_tabular_file(source_path, kind), output_path)
        print(f"{kind}: {count:,} rows")
        print(f"  input:  {source_path}")
        print(f"  output: {output_path}")


if __name__ == "__main__":
    main()
