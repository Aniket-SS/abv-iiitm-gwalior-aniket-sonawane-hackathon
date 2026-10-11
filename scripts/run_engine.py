from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.common.schemas import Signal
from src.engine.pipeline import RiskEngine
from src.ingestion.storage import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 3 NLP risk engine on normalized Document JSONL.")
    parser.add_argument("inputs", nargs="+", help="Input Document JSONL file(s)")
    parser.add_argument("--output", default="data/processed/signals.jsonl", help="Output Signal JSONL path")
    parser.add_argument("--limit", type=int, default=None, help="Maximum documents to process")
    parser.add_argument("--mode", choices=["auto", "rules"], default="auto",
                        help="auto tries transformer models then falls back; rules avoids model downloads")
    parser.add_argument("--no-spacy", action="store_true", help="Skip optional spaCy NER; alias linking still runs")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    documents = []
    for path in args.inputs:
        documents.extend(read_jsonl(path))
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be at least 1")
        documents = documents[:args.limit]
    if not documents:
        parser.error("No valid Documents found in the supplied JSONL inputs")

    model_mode = "auto" if args.mode == "auto" else "lexicon"
    event_mode = "auto" if args.mode == "auto" else "rules"
    engine = RiskEngine(sentiment_mode=model_mode, event_mode=event_mode, use_spacy=not args.no_spacy)
    signals = engine.run(documents)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for signal in signals:
            handle.write(signal.model_dump_json() + "\n")
    print(f"Processed {len(documents):,} documents -> {len(signals):,} signals")
    print(f"Output: {output}")
    print(f"Sentiment mode: {engine.sentiment_analyzer.mode}; event mode: {engine.event_classifier.mode}")
    print("Note: rules mode is a baseline, not a substitute for FinBERT/zero-shot inference or calibration.")


if __name__ == "__main__":
    main()
