from datetime import datetime, timezone
import json

from src.common.schemas import Channel, Document
from src.ingestion.normalization import entity_metadata, make_document, parse_datetime
from src.ingestion.storage import read_jsonl, write_jsonl


def test_parse_datetime_converts_to_utc():
    dt = parse_datetime("2026-10-10T12:00:00+05:30")
    assert dt == datetime(2026, 10, 10, 6, 30, tzinfo=timezone.utc)


def test_parse_gdelt_timestamp():
    dt = parse_datetime("20261010T120000Z")
    assert dt == datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def test_entity_scope_does_not_invent_ticker():
    meta = entity_metadata("Federal Reserve announces rate decision")
    assert meta["entity_scope"] == "market"
    assert meta["tickers"] == []


def test_document_jsonl_round_trip_and_dedupe(tmp_path):
    doc = make_document(
        source="test", channel=Channel.NEWS,
        timestamp=datetime(2026, 10, 10, tzinfo=timezone.utc),
        text="  Example   headline ", title="Example headline", url="https://example.com/a",
    )
    output = tmp_path / "docs.jsonl"
    assert write_jsonl([doc, doc], output) == 1
    restored = read_jsonl(output)
    assert len(restored) == 1
    assert restored[0].text == "Example headline"
    assert restored[0].channel == Channel.NEWS


def test_raw_metadata_serializes_as_json(tmp_path):
    doc = make_document(source="test", channel=Channel.SOCIAL,
        timestamp=datetime(2026, 10, 10, tzinfo=timezone.utc), text="text",
        raw_meta={"entity_scope": "company", "tickers": ["AAPL"]})
    line = doc.model_dump_json()
    parsed = json.loads(line)
    assert parsed["raw_meta"]["tickers"] == ["AAPL"]
