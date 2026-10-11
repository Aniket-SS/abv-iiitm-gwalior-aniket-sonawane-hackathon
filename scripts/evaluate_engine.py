from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from src.engine.sentiment import SentimentAnalyzer


def _label_from_score(score: float) -> str:
    if score > 0.12:
        return "positive"
    if score < -0.12:
        return "negative"
    return "neutral"


def _metrics(gold: list[str], predicted: list[str]) -> dict[str, object]:
    labels = ["negative", "neutral", "positive"]
    matrix = {actual: {guess: 0 for guess in labels} for actual in labels}
    for actual, guess in zip(gold, predicted):
        if actual in matrix and guess in matrix[actual]:
            matrix[actual][guess] += 1
    accuracy = sum(g == p for g, p in zip(gold, predicted)) / len(gold) if gold else 0.0
    f1_by_class: dict[str, float] = {}
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in labels if other != label)
        fn = sum(matrix[label][other] for other in labels if other != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1_by_class[label] = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"n": len(gold), "accuracy": round(accuracy, 4),
            "macro_f1": round(sum(f1_by_class.values()) / len(labels), 4),
            "class_f1": {k: round(v, 4) for k, v in f1_by_class.items()},
            "gold_distribution": dict(Counter(gold)), "confusion_matrix": matrix}


def _all_data(path: Path, limit: int | None) -> tuple[list[str], list[str]]:
    gold: list[str] = []
    predicted_texts: list[str] = []
    with path.open("r", encoding="cp1252", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if len(row) < 2:
                continue
            label, text = row[0].strip().lower(), row[1].strip()
            if label not in {"positive", "negative", "neutral"} or not text:
                continue
            gold.append(label)
            predicted_texts.append(text)
            if limit is not None and len(gold) >= limit:
                break
    return gold, predicted_texts


def _sentfin(path: Path, limit: int | None) -> tuple[list[str], list[str]]:
    gold: list[str] = []
    texts: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            title = (row.get("Title") or "").strip()
            if not title:
                continue
            try:
                decisions = json.loads(row.get("Decisions") or "{}")
            except json.JSONDecodeError:
                continue
            if not isinstance(decisions, dict):
                continue
            for entity, label in decisions.items():
                label = str(label).strip().lower()
                if label not in {"positive", "negative", "neutral"}:
                    continue
                gold.append(label)
                texts.append(f"{title} Entity: {entity}")
                if limit is not None and len(gold) >= limit:
                    return gold, texts
    return gold, texts


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate sentiment against SEntFiN or all-data.csv labels.")
    parser.add_argument("--dataset", choices=["all-data", "sentfin"], required=True)
    parser.add_argument("--input", required=True, help="Path to the local labelled CSV")
    parser.add_argument("--output", default="data/processed/evaluation.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--mode", choices=["auto", "finbert", "lexicon"], default="auto")
    args = parser.parse_args()
    path = Path(args.input)
    if not path.exists():
        parser.error(f"Dataset not found: {path}")
    gold, texts = _all_data(path, args.limit) if args.dataset == "all-data" else _sentfin(path, args.limit)
    if not gold:
        parser.error("No supported labeled examples found in dataset")
    analyzer = SentimentAnalyzer(mode=args.mode)
    predicted = [_label_from_score(analyzer.predict(text).score) for text in texts]
    result = {"dataset": args.dataset, "input": str(path), "mode_requested": args.mode,
              "model_backend": analyzer._backend or ("lexicon" if args.mode == "lexicon" else "auto/fallback"),
              "metrics": _metrics(gold, predicted),
              "limitations": ["SEntFiN labels are entity-level; entity text is appended to the headline.",
                              "Financial PhraseBank-style/all-data labels may overlap with FinBERT training data.",
                              "This script evaluates sentiment only, not event classification or impact calibration."]}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
