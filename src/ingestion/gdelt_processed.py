from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from src.common.schemas import Channel, Document


DEFAULT_INPUTS = [
    Path("data/processed/gdelt/gkg_latest.jsonl"),
]


def _stable_id(source: str, record_id: str, url: str | None) -> str:
    value = f"{source}|{record_id}|{url or ''}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _read_records(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}") from exc

            if isinstance(record, dict):
                yield record


def _make_document(record: dict[str, Any]) -> Document | None:
    source = str(record.get("source") or "gdelt_gkg")
    published_at = record.get("published_at")
    title = record.get("title")
    text = record.get("text")
    url = record.get("url")

    if not published_at:
        return None

    if not isinstance(text, str) or not text.strip():
        return None

    if not isinstance(title, str) or not title.strip():
        title = None

    record_id = str(record.get("source_record_id") or url or "")
    if not record_id:
        record_id = hashlib.sha256(text.encode("utf-8")).hexdigest()

    metadata = dict(record)
    metadata["entity_scope"] = record.get("entity_scope") or "unlinked"
    metadata["ticker"] = record.get("ticker")
    metadata["company"] = record.get("company")

    return Document(
        id=_stable_id(source, record_id, url),
        source=source,
        channel=Channel.NEWS,
        timestamp=published_at,
        text=text.strip(),
        title=title,
        url=url if isinstance(url, str) else None,
        raw_meta=metadata,
    )


def load_processed_gdelt(
    inputs: list[str | Path] | None = None,
) -> list[Document]:
    documents: list[Document] = []

    for item in inputs or DEFAULT_INPUTS:
        path = Path(item)
        for record in _read_records(path):
            document = _make_document(record)
            if document is not None:
                documents.append(document)

    return documents