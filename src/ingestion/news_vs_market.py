from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

from src.common.schemas import Channel, Document
from src.ingestion.normalization import entity_metadata, make_document, parse_datetime

DEFAULT_PATH = Path("data/raw/news_vs_market_2020/news_sentiment_raw.csv")


def read_news_vs_market(path: str | Path = DEFAULT_PATH, limit: int | None = None) -> Iterator[Document]:
    """Normalize the original article CSV; precomputed VADER values remain provenance metadata."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"News sentiment CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"published_at", "source", "topic", "title", "url", "compound", "pos", "neg", "neu", "sentiment_cat", "source_weight"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"Expected columns {sorted(required)}; found {reader.fieldnames}")
        count = 0
        for row in reader:
            title = (row.get("title") or "").strip()
            description = (row.get("description") or "").strip()
            text = " — ".join(part for part in (title, description) if part)
            timestamp = parse_datetime(row.get("published_at") or row.get("date"))
            if not text or timestamp is None:
                continue
            url = (row.get("url") or "").strip() or None
            metadata = entity_metadata(text, {
                "publisher": (row.get("source") or "").strip() or None,
                "topic": (row.get("topic") or "").strip() or None,
                "date": (row.get("date") or "").strip() or None,
                "source_sentiment": {
                    "method": "VADER (as reported by source dataset)",
                    "compound": _float(row.get("compound")),
                    "positive": _float(row.get("pos")),
                    "negative": _float(row.get("neg")),
                    "neutral": _float(row.get("neu")),
                    "category": (row.get("sentiment_cat") or "").strip() or None,
                    "source_weight": _float(row.get("source_weight")),
                },
                "content_note": "Title and description only; source-provided VADER values are not engine predictions.",
            })
            yield make_document(source="news_vs_market_2020", channel=Channel.NEWS,
                                timestamp=timestamp, text=text, title=title or None,
                                url=url, raw_meta=metadata)
            count += 1
            if limit is not None and count >= limit:
                break


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None and value.strip() else None
    except (TypeError, ValueError):
        return None
