from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

from src.common.config import PROJECT_ROOT, get_tickers
from src.common.schemas import Channel, Document
from src.ingestion.normalization import make_document, parse_datetime

DEFAULT_TWEETS_PATH = PROJECT_ROOT / "data/raw/stock_tweets/stock_tweets.csv"


def _resolve_ticker(stock_name: str, company_name: str) -> str | None:
    tickers = get_tickers()
    direct = (stock_name or "").strip().upper()
    if direct in tickers:
        return direct
    from src.ingestion.normalization import link_tickers
    for entity in link_tickers(f"{company_name or ''} {stock_name or ''}"):
        return entity["ticker"]
    return None


def read_tweets(path: str | Path = DEFAULT_TWEETS_PATH, limit: int | None = None) -> Iterator[Document]:
    """Read historical tweets and retain only records for the configured universe."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Tweet dataset not found: {path}")
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Date", "Tweet", "Stock Name", "Company Name"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"Expected columns {sorted(required)}; found {reader.fieldnames}")
        count = 0
        for row in reader:
            text = (row.get("Tweet") or "").strip()
            timestamp = parse_datetime(row.get("Date"))
            ticker = _resolve_ticker(row.get("Stock Name", ""), row.get("Company Name", ""))
            if not text or timestamp is None or ticker is None:
                continue
            cfg = get_tickers()[ticker]
            yield make_document(
                source="stock_tweets",
                channel=Channel.SOCIAL,
                timestamp=timestamp,
                text=text,
                raw_meta={
                    "entity_scope": "company",
                    "ticker": ticker,
                    "tickers": [ticker],
                    "company": cfg.company,
                    "original_stock_name": row.get("Stock Name"),
                    "original_company_name": row.get("Company Name"),
                },
            )
            count += 1
            if limit is not None and count >= limit:
                break
