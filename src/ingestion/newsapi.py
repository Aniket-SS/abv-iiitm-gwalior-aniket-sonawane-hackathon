from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import requests

from src.common.config import get_env
from src.common.schemas import Channel, Document
from src.ingestion.normalization import entity_metadata, make_document, parse_datetime

ENDPOINT = "https://newsapi.org/v2/everything"


def fetch_newsapi(query: str, page_size: int = 100, days_back: int = 7, timeout: int = 30) -> Iterator[Document]:
    """Fetch recent article headlines/descriptions. Does not fetch or store full article text."""
    api_key = get_env("NEWSAPI_API_KEY")
    if not api_key:
        raise RuntimeError("NEWSAPI_API_KEY is missing. Add it to .env; never commit the key.")
    if not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100")
    now = datetime.now(timezone.utc)
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "from": (now - timedelta(days=days_back)).date().isoformat(),
        "to": now.date().isoformat(),
        "apiKey": api_key,
    }
    response = requests.get(ENDPOINT, params=params, timeout=timeout)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"NewsAPI returned status={payload.get('status')}: {payload.get('message', 'unknown error')}")
    for article in payload.get("articles", []):
        title = (article.get("title") or "").strip()
        description = (article.get("description") or "").strip()
        text = " — ".join(part for part in (title, description) if part)
        timestamp = parse_datetime(article.get("publishedAt"))
        url = (article.get("url") or "").strip() or None
        if not text or not timestamp:
            continue
        source_info = article.get("source") or {}
        meta = entity_metadata(text, {
            "publisher": source_info.get("name"),
            "author": article.get("author"),
            "published_at_original": article.get("publishedAt"),
            "retrieved_from": "NewsAPI",
            "content_note": "Headline and description only; not full article text.",
        })
        yield make_document(source="newsapi", channel=Channel.NEWS, timestamp=timestamp,
                            text=text, title=title or None, url=url, raw_meta=meta)
