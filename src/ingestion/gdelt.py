from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

HISTORICAL_START = "2021-09-30"
HISTORICAL_END = "2022-09-29"

SELECTED_TICKERS = {
    "AAPL", "AMD", "AMZN", "BA", "COST", "CRM", "DIS", "GOOG",
    "INTC", "KO", "META", "MSFT", "NFLX", "PG", "TSLA", "VZ",
}


def _split_semicolon(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def _metadata_tag(metadata: str, tag: str) -> str | None:
    match = re.search(
        rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>",
        metadata or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    value = html.unescape(match.group(1)).strip()
    return value or None


def _parse_gdelt_datetime(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return None


def _float_or_none(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_gkg_row(row: list[str]) -> dict[str, Any] | None:
    if len(row) < 27:
        return None
    metadata = row[26]
    title = _metadata_tag(metadata, "PAGE_TITLE")
    url = (row[4] or "").strip()
    if not title and not url:
        return None

    raw_timestamp = _metadata_tag(metadata, "PAGE_PRECISEPUBTIMESTAMP") or row[1]
    return {
        "source": "gdelt_gkg",
        "source_record_id": (row[0] or "").strip() or None,
        "published_at": _parse_gdelt_datetime(raw_timestamp),
        "publisher": (row[3] or "").strip() or None,
        "title": title,
        "url": url or None,
        "themes": _split_semicolon(row[7]),
        "locations": _split_semicolon(row[9]),
        "persons": _split_semicolon(row[10]),
        "organizations": _split_semicolon(row[23]),
        "gdelt_tone": _float_or_none((row[15] or "").split(",", 1)[0]),
        "text": title,
        "ticker": None,
        "company": None,
        "entity_scope": "unlinked",
        "sentiment_score": None,
        "event_type": None,
        "impact_score": None,
        "raw_gdelt_timestamp": (row[1] or "").strip() or None,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_export_row(row: list[str]) -> dict[str, Any] | None:
    if len(row) < 58:
        return None
    return {
        "source": "gdelt_export",
        "source_record_id": (row[0] or "").strip() or None,
        "published_at": _parse_gdelt_datetime((row[1] or "").strip()),
        "event_code": (row[26] or "").strip() or None,
        "event_base_code": (row[27] or "").strip() or None,
        "event_root_code": (row[28] or "").strip() or None,
        "event_quad_class": (row[29] or "").strip() or None,
        "goldstein_scale": _float_or_none(row[30]),
        "num_mentions": _int_or_none(row[31]),
        "num_sources": _int_or_none(row[32]),
        "num_articles": _int_or_none(row[33]),
        "avg_tone": _float_or_none(row[34]),
        "actor1_name": (row[6] or "").strip() or None,
        "actor2_name": (row[16] or "").strip() or None,
        "action_geo_country_code": (row[51] or "").strip() or None,
        "ticker": None,
        "company": None,
        "entity_scope": "unlinked",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_mentions_row(row: list[str]) -> dict[str, Any] | None:
    if len(row) < 16:
        return None
    return {
        "source": "gdelt_mentions",
        "source_record_id": (row[0] or "").strip() or None,
        "event_date": _parse_gdelt_datetime((row[1] or "").strip()),
        "published_at": _parse_gdelt_datetime((row[2] or "").strip()),
        "mention_type": (row[3] or "").strip() or None,
        "mention_source_name": (row[4] or "").strip() or None,
        "mention_identifier": (row[5] or "").strip() or None,
        "sentence_id": _int_or_none(row[6]),
        "actor1_char_offset": _int_or_none(row[7]),
        "actor2_char_offset": _int_or_none(row[8]),
        "action_char_offset": _int_or_none(row[9]),
        "in_raw_text": (row[10] or "").strip() or None,
        "confidence": _int_or_none(row[11]),
        "mention_doc_length": _int_or_none(row[12]),
        "mention_doc_tone": _float_or_none(row[13]),
        "mention_doc_translation_info": (row[14] or "").strip() or None,
        "extras": (row[15] or "").strip() or None,
        "ticker": None,
        "company": None,
        "entity_scope": "unlinked",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def read_tabular_file(path: Path, kind: str) -> Iterable[dict[str, Any]]:
    parser = {"gkg": parse_gkg_row, "export": parse_export_row, "mentions": parse_mentions_row}[kind]
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            record = parser(row)
            if record is not None:
                yield record


def write_jsonl(records: Iterable[dict[str, Any]], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count
