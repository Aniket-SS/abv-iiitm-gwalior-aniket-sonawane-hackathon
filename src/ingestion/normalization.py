from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from src.common.config import get_tickers
from src.common.schemas import Channel, Document


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
            try:
                parsed = datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def stable_id(source: str, url: str | None, title: str | None, text: str, timestamp: datetime) -> str:
    identity = (url or "").strip() or f"{title or ''}|{text}|{timestamp.isoformat()}"
    return hashlib.sha256(f"{source}|{identity}".encode("utf-8")).hexdigest()[:24]


def _contains_alias(text: str, alias: str) -> bool:
    alias = alias.strip()
    if not alias:
        return False
    if len(alias) <= 3 and alias.isalpha():
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text, re.I))
    return bool(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.I))


def link_tickers(text: str) -> list[dict[str, str]]:
    """Return all configured tickers with a matching company alias; never guess a ticker."""
    found: list[dict[str, str]] = []
    for ticker, cfg in get_tickers().items():
        candidates = [cfg.company, ticker, *cfg.aliases]
        if any(_contains_alias(text, alias) for alias in candidates):
            found.append({"ticker": ticker, "company": cfg.company})
    return found


def make_document(
    *, source: str, channel: Channel, timestamp: datetime, text: str,
    title: str | None = None, url: str | None = None,
    raw_meta: dict[str, Any] | None = None,
) -> Document:
    clean_text = " ".join((text or "").split())
    clean_title = " ".join((title or "").split()) or None
    return Document(
        id=stable_id(source, url, clean_title, clean_text, timestamp),
        source=source,
        channel=channel,
        timestamp=timestamp,
        text=clean_text,
        title=clean_title,
        url=url or None,
        raw_meta=raw_meta or {},
    )


def entity_metadata(text: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    linked = link_tickers(text)
    metadata: dict[str, Any] = {
        "entity_scope": "company" if linked else "market",
        "entities": linked,
        "tickers": [item["ticker"] for item in linked],
    }
    if extra:
        metadata.update(extra)
    return metadata


def deduplicate(documents: Iterable[Document]) -> list[Document]:
    seen: set[str] = set()
    result: list[Document] = []
    for doc in documents:
        key = doc.url.strip().lower().rstrip("/") if doc.url else doc.id
        if key in seen:
            continue
        seen.add(key)
        result.append(doc)
    return result
