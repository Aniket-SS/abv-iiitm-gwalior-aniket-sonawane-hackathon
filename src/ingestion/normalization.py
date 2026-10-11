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


def stable_id(
    source: str, url: str | None, title: str | None, text: str, timestamp: datetime,
    salt: str | None = None,
) -> str:
    """Deterministic document id.

    `salt` is extra identity for sources where the SAME text legitimately belongs to
    several records (e.g. one tweet tagged with two tickers). Without a salt the id is
    exactly what it was before, so ids of other sources do not change.
    """
    identity = (url or "").strip() or f"{title or ''}|{text}|{timestamp.isoformat()}"
    if salt:
        identity = f"{identity}|{salt}"
    return hashlib.sha256(f"{source}|{identity}".encode("utf-8")).hexdigest()[:24]


# --------------------------------------------------------------------------- ticker linking
# Matching is deliberately conservative: a missed link is better than an invented one.
#
# Evidence tiers (strongest first):
#   cashtag : "$TSLA" (case-insensitive, the "$" makes it unambiguous)
#   symbol  : "AAPL" written in UPPER case as a whole word (case-sensitive).
#             Symbols that are also common words/abbreviations (COST, BA, KO, ...) are
#             accepted only with an exchange prefix such as "(NASDAQ: COST)" or "NYSE: KO".
#   name    : company names/aliases as whole words. Unambiguous names ("Tesla", "Netflix")
#             match in any case; ambiguous names ("Apple", "Meta", ...) must match the exact
#             capitalisation used in config/tickers.yaml and must not be followed by an
#             obvious non-company continuation ("Apple pie", "Amazon river", "Meta-analysis").
#
# If you add a ticker whose symbol/name is also an everyday word, add it to the sets below.
AMBIGUOUS_SYMBOLS = frozenset({"BA", "COST", "CRM", "DIS", "KO", "META", "PG"})

# alias (exact case) -> regex lookahead that REJECTS the match when it follows the alias
AMBIGUOUS_NAMES: dict[str, str] = {
    "Apple": r"(?!\s+(?:pie|pies|juice|tree|trees|cider|orchard|orchards|sauce)\b)",
    "Amazon": r"(?!\s+(?:river|rainforest|basin|forest|jungle)\b)",
    "Meta": r"(?!-(?:analysis|analyses|data|physics)\b)",
    "Intel": "",
    "Coke": "",
    "AWS": "",
}

_CASHTAG_RE = re.compile(r"(?<![\w$])\$([A-Za-z]{1,5})(?![A-Za-z0-9])")


def _symbol_matches(text: str, ticker: str) -> bool:
    if ticker in AMBIGUOUS_SYMBOLS:
        pattern = rf"(?i:nyse|nasdaq\w*)\s*:\s*{re.escape(ticker)}(?![A-Za-z0-9])"
    else:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])"
    return re.search(pattern, text) is not None  # case-sensitive on purpose


def _name_matches(text: str, alias: str) -> bool:
    alias = alias.strip()
    if not alias:
        return False
    if alias in AMBIGUOUS_NAMES:
        pattern = rf"(?<!\w){re.escape(alias)}(?!\w){AMBIGUOUS_NAMES[alias]}"
        return re.search(pattern, text) is not None  # exact capitalisation only
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.IGNORECASE) is not None


def link_tickers(text: str) -> list[dict[str, str]]:
    """Return configured tickers that the text mentions, with the kind of evidence found.

    Each item: {"ticker", "company", "match"} where match is "cashtag", "symbol" or "name".
    Never guesses: no evidence -> no link.
    """
    cashtags = {tag.upper() for tag in _CASHTAG_RE.findall(text or "")}
    found: list[dict[str, str]] = []
    for ticker, cfg in get_tickers().items():
        if ticker in cashtags:
            method = "cashtag"
        elif _symbol_matches(text or "", ticker):
            method = "symbol"
        elif any(_name_matches(text or "", alias) for alias in (cfg.company, *cfg.aliases)):
            method = "name"
        else:
            continue
        found.append({"ticker": ticker, "company": cfg.company, "match": method})
    return found


def make_document(
    *, source: str, channel: Channel, timestamp: datetime, text: str,
    title: str | None = None, url: str | None = None,
    raw_meta: dict[str, Any] | None = None, id_salt: str | None = None,
) -> Document:
    clean_text = " ".join((text or "").split())
    clean_title = " ".join((title or "").split()) or None
    return Document(
        id=stable_id(source, url, clean_title, clean_text, timestamp, salt=id_salt),
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
