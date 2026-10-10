"""Core data contracts shared by every part of the pipeline.

Document : one raw item produced by an ingestion adapter (a news article, a tweet, ...).
Signal   : one structured output of the NLP engine for ONE (document, ticker) pair.

Everything downstream (signal store, API, rebalancer, stress tester, dashboard)
consumes `Signal`. Keep this file small and stable: changing it affects every module.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SNIPPET_MAX_CHARS = 300


class Channel(str, Enum):
    """Kind of source. The case study asks for at least two different sources."""

    NEWS = "news"
    SOCIAL = "social"


class EventType(str, Enum):
    """Event classes. Must stay in sync with the keys of config/event_taxonomy.yaml."""

    GEOPOLITICAL = "geopolitical"
    MACROECONOMIC = "macroeconomic"
    CREDIT_EVENT = "credit_event"
    MERGER_ACQUISITION = "merger_acquisition"
    PRODUCT_LAUNCH = "product_launch"
    EARNINGS = "earnings"
    REGULATORY_LEGAL = "regulatory_legal"
    LEADERSHIP_CHANGE = "leadership_change"
    OPERATIONAL_DISRUPTION = "operational_disruption"
    OTHER = "other"


def _to_utc(value: datetime) -> datetime:
    """Naive datetimes are assumed to be UTC; aware ones are converted to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Document(BaseModel):
    """A raw text item from any source, in one common shape."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, description="Unique within a source, e.g. article URL hash")
    source: str = Field(min_length=1, description="Adapter name, e.g. 'gdelt', 'kaggle_news'")
    channel: Channel
    timestamp: datetime = Field(description="Publication time; stored as UTC")
    text: str = Field(min_length=1)
    title: str | None = None
    url: str | None = None
    raw_meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_utc(cls, v: datetime) -> datetime:
        return _to_utc(v)


class Signal(BaseModel):
    """Engine output for one (document, ticker) pair. This is the API payload."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    signal_id: str = Field(min_length=1, description="Deterministic: see make_signal_id()")
    doc_id: str = Field(min_length=1)
    timestamp: datetime = Field(description="Time of the underlying document, UTC")
    source: str
    channel: Channel
    ticker: str = Field(min_length=1)
    company: str | None = None
    sentiment: float = Field(ge=-1.0, le=1.0, description="-1 very negative ... +1 very positive")
    event_type: EventType
    impact: float = Field(ge=1.0, le=10.0, description="1 negligible ... 10 severe")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    text_snippet: str = Field(default="", max_length=SNIPPET_MAX_CHARS)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_utc(cls, v: datetime) -> datetime:
        return _to_utc(v)

    @field_validator("ticker")
    @classmethod
    def _ticker_upper(cls, v: str) -> str:
        return v.upper()


def make_signal_id(doc_id: str, ticker: str) -> str:
    """Deterministic id, so re-running the pipeline on the same data is idempotent."""
    raw = f"{doc_id}|{ticker.upper()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def make_snippet(text: str, max_chars: int = SNIPPET_MAX_CHARS) -> str:
    """Whitespace-collapsed, length-limited excerpt that always fits Signal.text_snippet."""
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"
