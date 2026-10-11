from __future__ import annotations

import time
from typing import Any, Iterator

import requests

from src.common.schemas import Channel, Document
from src.ingestion.normalization import entity_metadata, make_document, parse_datetime

ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"


def fetch_gdelt(query: str, timespan: str = "1week", max_records: int = 100, timeout: int = 30) -> Iterator[Document]:
    """Fetch recent article metadata from GDELT DOC API; this is not historical replay data."""
    if not 1 <= max_records <= 250:
        raise ValueError("max_records must be between 1 and 250")
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "sort": "HybridRel",
        "timespan": timespan,
        "maxrecords": max_records,
    }
    response = requests.get(ENDPOINT, params=params, timeout=timeout)
    if response.status_code == 429:
        raise RuntimeError("GDELT rate limit reached (HTTP 429). Wait at least 5 seconds before retrying.")
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    for article in payload.get("articles", []):
        title = (article.get("title") or "").strip()
        url = (article.get("url") or "").strip() or None
        timestamp = parse_datetime(article.get("seendate"))
        if not timestamp or not title:
            continue
        meta = entity_metadata(title, {
            "publisher": article.get("domain"),
            "language": article.get("language"),
            "source_country": article.get("sourceCountry"),
            "seen_date": article.get("seendate"),
            "retrieved_from": "GDELT DOC API",
        })
        yield make_document(source="gdelt", channel=Channel.NEWS, timestamp=timestamp,
                            text=title, title=title, url=url, raw_meta=meta)


def fetch_queries(queries: list[str], timespan: str = "1week", max_records: int = 100) -> Iterator[Document]:
    """Run multiple queries with a minimum five-second pause between calls."""
    for index, query in enumerate(queries):
        if index:
            time.sleep(5.1)
        yield from fetch_gdelt(query, timespan=timespan, max_records=max_records)
