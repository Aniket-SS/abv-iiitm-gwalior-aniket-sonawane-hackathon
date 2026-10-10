from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.common.schemas import (
    Channel,
    Document,
    EventType,
    Signal,
    make_signal_id,
    make_snippet,
)


def _signal(**overrides) -> Signal:
    data = dict(
        signal_id=make_signal_id("doc-1", "aapl"),
        doc_id="doc-1",
        timestamp=datetime(2026, 1, 15, 9, 30),
        source="kaggle_news",
        channel=Channel.NEWS,
        ticker="aapl",
        company="Apple Inc.",
        sentiment=0.6,
        event_type=EventType.PRODUCT_LAUNCH,
        impact=3.5,
        confidence=0.82,
        rationale="Positive launch coverage.",
        text_snippet="Apple unveils ...",
    )
    data.update(overrides)
    return Signal(**data)


def test_signal_json_round_trip():
    sig = _signal()
    restored = Signal.model_validate_json(sig.model_dump_json())
    assert restored == sig
    assert sig.model_dump(mode="json")["event_type"] == "product_launch"


def test_ticker_is_uppercased_and_naive_time_becomes_utc():
    sig = _signal()
    assert sig.ticker == "AAPL"
    assert sig.timestamp.tzinfo is not None
    assert sig.timestamp.utcoffset() == timedelta(0)


def test_aware_timestamp_is_converted_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    sig = _signal(timestamp=datetime(2026, 1, 15, 15, 0, tzinfo=ist))
    assert sig.timestamp == datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "field,value",
    [("sentiment", 1.5), ("impact", 0.5), ("impact", 11), ("confidence", -0.1)],
)
def test_out_of_range_values_rejected(field, value):
    with pytest.raises(ValidationError):
        _signal(**{field: value})


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        _signal(sentimnt=0.2)  # typo should not pass silently


def test_signal_id_is_deterministic_and_case_insensitive():
    assert make_signal_id("d1", "aapl") == make_signal_id("d1", "AAPL")
    assert make_signal_id("d1", "AAPL") != make_signal_id("d2", "AAPL")


def test_snippet_is_limited_and_whitespace_collapsed():
    text = "word  " * 500
    snippet = make_snippet(text)
    assert len(snippet) <= 300
    assert "  " not in snippet
    _signal(text_snippet=snippet)  # must satisfy the Signal constraint


def test_document_requires_text():
    with pytest.raises(ValidationError):
        Document(id="1", source="gdelt", channel=Channel.NEWS,
                 timestamp=datetime(2026, 1, 1), text="")
