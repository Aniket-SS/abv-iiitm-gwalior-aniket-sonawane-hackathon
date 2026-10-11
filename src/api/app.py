from __future__ import annotations

from contextlib import asynccontextmanager
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query

import joblib
import pandas as pd

from src.market.learned_impact import FEATURES

from src.common.config import get_settings
from src.common.schemas import Signal
from src.signals.store import SignalStore


_store: SignalStore | None = None


def get_store() -> SignalStore:
    global _store
    if _store is None:
        db_override = os.getenv("SIGNALS_DB_PATH")
        _store = SignalStore(db_override) if db_override else SignalStore()
    return _store


_impact_model = None


def get_impact_model():
    global _impact_model

    if _impact_model is not None:
        return _impact_model

    model_path = Path(
        os.getenv(
            "IMPACT_MODEL_PATH",
            "data/processed/phase5/learned_impact_model.joblib",
        )
    )

    if not model_path.is_absolute():
        model_path = Path.cwd() / model_path

    if not model_path.is_file():
        raise HTTPException(
            status_code=503,
            detail="Learned impact model is unavailable.",
        )

    try:
        _impact_model = joblib.load(model_path)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not load learned impact model.",
        ) from exc

    return _impact_model


def score_signal_with_model(signal: dict) -> dict:
    model = get_impact_model()

    features = {
        "impact": float(signal["impact"]),
        "confidence": float(signal["confidence"]),
        "abs_sentiment": abs(float(signal["sentiment"])),
        "event_type": str(signal["event_type"]),
        "channel": str(signal["channel"]),
        "scope": str(signal["scope"]),
        "ticker": str(signal["ticker"]).upper(),
    }

    frame = pd.DataFrame([features], columns=FEATURES)

    predicted_magnitude = float(model.predict_magnitude(frame)[0])
    calibrated_score = float(model.predict(frame)[0])

    return {
        "original_impact": float(signal["impact"]),
        "predicted_abs_abnormal_return_pct": round(
            predicted_magnitude, 6
        ),
        "calibrated_impact_score": round(calibrated_score, 4),
        "horizon_trading_days": 3,
        "experimental": True,
        "model_status": "experimental_unvalidated",
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store().initialize()
    yield


app = FastAPI(
    title="Code to Connect Signal API",
    description="SQLite-backed access to NLP-generated market and company risk signals.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health(store: SignalStore = Depends(get_store)) -> dict[str, object]:
    return {"status": "ok", "database": str(store.db_path), "signal_count": store.count()}


@app.get("/signals/{signal_id}/impact-calibration")
def get_calibrated_impact(
    signal_id: str,
    store: SignalStore = Depends(get_store),
) -> dict[str, object]:
    signal = store.get(signal_id)

    if signal is None:
        raise HTTPException(
            status_code=404,
            detail="Signal not found",
        )

    return {
        "signal_id": signal_id,
        **score_signal_with_model(signal),
    }

@app.get("/signals")
def list_signals(
    ticker: str | None = None,
    source: str | None = None,
    channel: Literal["news", "social"] | None = None,
    scope: Literal["company", "market"] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    store: SignalStore = Depends(get_store),
) -> dict[str, object]:
    if since and until and since > until:
        raise HTTPException(status_code=422, detail="since must be earlier than or equal to until")
    items = store.list_signals(
        ticker=ticker, source=source, channel=channel, scope=scope,
        since=since, until=until, limit=limit, offset=offset,
    )
    return {"count": len(items), "limit": limit, "offset": offset, "items": items}


@app.get("/signals/aggregate")
def aggregate_signals(
    as_of: datetime | None = None,
    window_days: int = Query(default=7, ge=1, le=90),
    half_life_hours: float = Query(default=48.0, gt=0, le=8760),
    min_confidence: float = Query(default=0.5, ge=0, le=1),
    store: SignalStore = Depends(get_store),
) -> dict[str, object]:
    items = store.aggregate(
        now=as_of,
        window_days=window_days,
        half_life_hours=half_life_hours,
        min_confidence=min_confidence,
    )
    return {"count": len(items), "items": items}


@app.get("/signals/{signal_id}")
def get_signal(signal_id: str, store: SignalStore = Depends(get_store)) -> dict[str, object]:
    item = store.get(signal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return item
