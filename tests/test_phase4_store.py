from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.api import app as api_module
from src.api.app import app
from src.common.schemas import Channel, EventType, Signal, make_signal_id
from src.signals.store import SignalStore


def make_signal(doc_id: str, ticker: str, *, sentiment: float = 0.5, confidence: float = 0.9, hours_ago: int = 1) -> Signal:
    return Signal(
        signal_id=make_signal_id(doc_id, ticker),
        doc_id=doc_id,
        timestamp=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        source="test_source",
        channel=Channel.NEWS,
        ticker=ticker,
        scope="company",
        company=f"{ticker} Company",
        sentiment=sentiment,
        event_type=EventType.OTHER,
        impact=3.0,
        confidence=confidence,
        rationale="test",
        text_snippet="synthetic test signal",
    )


def test_store_upsert_is_idempotent(tmp_path):
    store = SignalStore(tmp_path / "test.db")
    signals = [make_signal("doc1", "AAPL"), make_signal("doc2", "MSFT")]
    assert store.upsert_many(signals) == 2
    assert store.count() == 2
    store.upsert_many(signals)
    assert store.count() == 2
    assert store.get(signals[0].signal_id)["ticker"] == "AAPL"


def test_store_filters_and_aggregate(tmp_path):
    store = SignalStore(tmp_path / "test.db")
    store.upsert_many([
        make_signal("doc1", "AAPL", sentiment=0.8),
        make_signal("doc2", "AAPL", sentiment=-0.2, hours_ago=24),
        make_signal("doc3", "MSFT", sentiment=0.1, confidence=0.2),
    ])
    assert len(store.list_signals(ticker="aapl")) == 2
    aggregate = store.aggregate(min_confidence=0.5)
    assert len(aggregate) == 1
    assert aggregate[0]["ticker"] == "AAPL"
    assert aggregate[0]["signal_count"] == 2
    assert -1 <= aggregate[0]["weighted_sentiment"] <= 1


def test_api_health_list_and_not_found(tmp_path, monkeypatch):
    store = SignalStore(tmp_path / "api.db")
    store.upsert_many([make_signal("doc1", "AAPL")])
    monkeypatch.setattr(api_module, "_store", store)
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["signal_count"] == 1
        assert client.get("/signals?ticker=AAPL").json()["count"] == 1
        assert client.get("/signals/not-present").status_code == 404
