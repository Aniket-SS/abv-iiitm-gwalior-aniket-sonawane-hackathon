from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.common.config import get_settings, resolve_path
from src.common.schemas import Signal


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _signal_record(signal: Signal) -> tuple[Any, ...]:
    return (
        signal.signal_id,
        signal.doc_id,
        _utc_iso(signal.timestamp),
        signal.source,
        signal.channel.value,
        signal.ticker.upper(),
        signal.scope,
        signal.company,
        signal.sentiment,
        signal.event_type.value,
        signal.impact,
        signal.confidence,
        signal.rationale,
        signal.text_snippet,
    )


class SignalStore:
    def __init__(self, db_path: str | Path | None = None):
        configured = get_settings().paths.signals_db
        self.db_path = Path(db_path) if db_path is not None else resolve_path(configured)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    channel TEXT NOT NULL CHECK(channel IN ('news', 'social')),
                    ticker TEXT NOT NULL,
                    scope TEXT NOT NULL CHECK(scope IN ('company', 'market')),
                    company TEXT,
                    sentiment REAL NOT NULL CHECK(sentiment >= -1 AND sentiment <= 1),
                    event_type TEXT NOT NULL,
                    impact REAL NOT NULL CHECK(impact >= 1 AND impact <= 10),
                    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                    rationale TEXT NOT NULL DEFAULT '',
                    text_snippet TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_ticker_timestamp ON signals(ticker, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_channel ON signals(channel)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_scope ON signals(scope)")

    def upsert_many(self, signals: Iterable[Signal]) -> int:
        rows = [_signal_record(signal) for signal in signals]
        if not rows:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO signals (
                    signal_id, doc_id, timestamp, source, channel, ticker, scope, company,
                    sentiment, event_type, impact, confidence, rationale, text_snippet
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(signal_id) DO UPDATE SET
                    doc_id=excluded.doc_id,
                    timestamp=excluded.timestamp,
                    source=excluded.source,
                    channel=excluded.channel,
                    ticker=excluded.ticker,
                    scope=excluded.scope,
                    company=excluded.company,
                    sentiment=excluded.sentiment,
                    event_type=excluded.event_type,
                    impact=excluded.impact,
                    confidence=excluded.confidence,
                    rationale=excluded.rationale,
                    text_snippet=excluded.text_snippet
                """,
                rows,
            )
        return len(rows)

    def count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0])

    def get(self, signal_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,)).fetchone()
        return dict(row) if row else None

    def list_signals(
        self,
        *,
        ticker: str | None = None,
        source: str | None = None,
        channel: str | None = None,
        scope: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (("ticker", ticker.upper() if ticker else None), ("source", source), ("channel", channel), ("scope", scope)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(_utc_iso(since))
        if until is not None:
            clauses.append("timestamp <= ?")
            params.append(_utc_iso(until))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM signals {where} ORDER BY timestamp DESC, signal_id LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def aggregate(
        self,
        *,
        now: datetime | None = None,
        window_days: int | None = None,
        half_life_hours: float | None = None,
        min_confidence: float | None = None,
    ) -> list[dict[str, Any]]:
        settings = get_settings().signals
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        window_days = window_days or settings.window_days
        half_life_hours = half_life_hours or settings.decay_half_life_hours
        min_confidence = settings.min_confidence if min_confidence is None else min_confidence
        if window_days < 1 or half_life_hours <= 0 or not 0 <= min_confidence <= 1:
            raise ValueError("Invalid aggregation parameters")
        cutoff = now.timestamp() - window_days * 86400
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE timestamp >= ? AND timestamp <= ? AND confidence >= ?",
                (datetime.fromtimestamp(cutoff, timezone.utc).isoformat(), now.isoformat(), min_confidence),
            ).fetchall()
        groups: dict[tuple[str, str], list[tuple[dict[str, Any], float]]] = {}
        for raw in rows:
            row = dict(raw)
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            age_hours = max(0.0, (now - timestamp.astimezone(timezone.utc)).total_seconds() / 3600)
            weight = 0.5 ** (age_hours / half_life_hours) * row["confidence"]
            groups.setdefault((row["ticker"], row["scope"]), []).append((row, weight))
        result: list[dict[str, Any]] = []
        for (ticker, scope), items in sorted(groups.items()):
            weight_sum = sum(weight for _, weight in items)
            sentiment = sum(row["sentiment"] * weight for row, weight in items) / weight_sum if weight_sum else 0.0
            impact = sum(row["impact"] * weight for row, weight in items) / weight_sum if weight_sum else 0.0
            result.append({
                "ticker": ticker,
                "scope": scope,
                "signal_count": len(items),
                "weighted_sentiment": round(sentiment, 6),
                "weighted_impact": round(impact, 6),
                "mean_confidence": round(sum(row["confidence"] for row, _ in items) / len(items), 6),
                "latest_timestamp": max(row["timestamp"] for row, _ in items),
                "window_days": window_days,
                "half_life_hours": half_life_hours,
                "min_confidence": min_confidence,
            })
        return result


def load_jsonl(path: str | Path) -> tuple[list[Signal], int]:
    signals: list[Signal] = []
    invalid = 0
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                signals.append(Signal.model_validate(json.loads(line)))
            except Exception as exc:
                invalid += 1
                raise ValueError(f"Invalid signal at line {line_no}: {exc}") from exc
    return signals, invalid
