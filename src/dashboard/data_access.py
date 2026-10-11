from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def database_path() -> Path:
    configured = os.getenv("SIGNALS_DB_PATH", "data/processed/signals.db")
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def price_path() -> Path:
    configured = os.getenv("PRICES_CSV_PATH", "data/raw/prices/prices_daily.csv")
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def _read_signals(query: str, params: tuple = ()) -> pd.DataFrame:
    path = database_path()
    if not path.exists():
        return pd.DataFrame()
    with sqlite3.connect(str(path)) as conn:
        return pd.read_sql_query(query, conn, params=params)


def all_signals() -> pd.DataFrame:
    """Return every stored signal for full-database analytics, newest first."""
    return _read_signals(
        "SELECT signal_id, timestamp, source, channel, ticker, scope, company, "
        "sentiment, event_type, impact, confidence FROM signals ORDER BY timestamp DESC"
    )


def recent_signals(limit: int = 500, min_impact: float | None = None) -> pd.DataFrame:
    query = (
        "SELECT signal_id, timestamp, source, channel, ticker, scope, company, "
        "sentiment, event_type, impact, confidence, rationale, text_snippet FROM signals"
    )
    params: list[object] = []
    if min_impact is not None:
        query += " WHERE impact >= ?"
        params.append(float(min_impact))
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(int(limit))
    return _read_signals(query, tuple(params))


def qualifying_signals(
    min_impact: float = 7.0,
    since_days: int = 90,
    scope: str = "all",
    event_type: str = "all",
    display_limit: int = 2000,
) -> pd.DataFrame:
    """Filter the full database in SQL; limit only the number of selector options shown."""
    query = (
        "SELECT signal_id, timestamp, source, channel, ticker, scope, company, "
        "sentiment, event_type, impact, confidence, text_snippet FROM signals "
        "WHERE CAST(impact AS REAL) >= ? "
        "AND datetime(timestamp) >= datetime('now', ?)"
    )
    params: list[object] = [float(min_impact), f"-{int(since_days)} days"]
    if scope and scope.lower() != "all":
        query += " AND lower(trim(coalesce(scope, ''))) = ?"
        params.append(scope.strip().lower())
    if event_type and event_type.lower() != "all":
        query += " AND lower(replace(replace(replace(trim(coalesce(event_type, 'other')), ' ', '_'), '/', '_'), '-', '_')) = ?"
        params.append(event_type.strip().lower().replace(" ", "_"))
    query += " ORDER BY datetime(timestamp) DESC LIMIT ?"
    params.append(int(display_limit))
    return _read_signals(query, tuple(params))


def event_type_counts() -> pd.DataFrame:
    return _read_signals(
        "SELECT lower(trim(coalesce(event_type, 'other'))) AS event_type, "
        "COUNT(*) AS signals FROM signals "
        "GROUP BY lower(trim(coalesce(event_type, 'other'))) ORDER BY signals DESC"
    )


def signal_count() -> int:
    path = database_path()
    if not path.exists():
        return 0
    with sqlite3.connect(str(path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM signals").fetchone()
    return int(row[0]) if row else 0
