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


def recent_signals(limit: int = 500, min_impact: float | None = None) -> pd.DataFrame:
    path = database_path()
    if not path.exists():
        return pd.DataFrame()
    query = "SELECT signal_id, timestamp, source, channel, ticker, scope, company, sentiment, event_type, impact, confidence, rationale, text_snippet FROM signals"
    params: list[object] = []
    if min_impact is not None:
        query += " WHERE impact >= ?"
        params.append(float(min_impact))
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(int(limit))
    with sqlite3.connect(str(path)) as conn:
        return pd.read_sql_query(query, conn, params=params)


def signal_count() -> int:
    path = database_path()
    if not path.exists():
        return 0
    with sqlite3.connect(str(path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM signals").fetchone()
    return int(row[0]) if row else 0
