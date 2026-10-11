"""Train and evaluate a chronological learned impact-score calibration layer.

The model estimates the magnitude of subsequent abnormal returns from existing
signal features. It is a research baseline, not investment advice or a guarantee
of predictive performance.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

from src.market.calibration import spearman

NUMERIC_FEATURES = ["impact", "confidence", "abs_sentiment"]
CATEGORICAL_FEATURES = ["event_type", "channel", "scope", "ticker"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def load_event_rows(path: str | Path, horizon: int = 3) -> list[dict[str, Any]]:
    """Load valid event-study observations and attach the selected target."""
    target_col = f"abnormal_return_pct_{horizon}d"
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                target = float(row.get(target_col, ""))
                impact = float(row["impact"])
                confidence = float(row.get("confidence", 0.0))
                sentiment = float(row.get("sentiment", 0.0))
                event_day = date.fromisoformat(row["event_date"])
            except (TypeError, ValueError, KeyError):
                continue
            if not all(math.isfinite(x) for x in (target, impact, confidence, sentiment)):
                continue
            item = {
                "event_date": event_day.isoformat(),
                "ticker": str(row.get("outcome_ticker") or row.get("ticker") or "UNKNOWN").upper(),
                "impact": min(10.0, max(1.0, impact)),
                "confidence": min(1.0, max(0.0, confidence)),
                "abs_sentiment": abs(min(1.0, max(-1.0, sentiment))),
                "event_type": str(row.get("event_type") or "other"),
                "channel": str(row.get("channel") or "unknown"),
                "scope": str(row.get("scope") or "company"),
                "target_abs_abnormal_return_pct": abs(target),
            }
            rows.append(item)
    return rows


def aggregate_correlated_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate same ticker/date observations to reduce duplicate-event leakage."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["ticker"], row["event_date"]), []).append(row)
    aggregated = []
    for (ticker, event_date), items in sorted(groups.items()):
        def mode(field: str) -> str:
            return Counter(str(item[field]) for item in items).most_common(1)[0][0]
        aggregated.append({
            "event_date": event_date,
            "ticker": ticker,
            "impact": max(float(item["impact"]) for item in items),
            "confidence": sum(float(item["confidence"]) for item in items) / len(items),
            "abs_sentiment": sum(float(item["abs_sentiment"]) for item in items) / len(items),
            "event_type": mode("event_type"),
            "channel": mode("channel"),
            "scope": mode("scope"),
            "target_abs_abnormal_return_pct": sum(float(item["target_abs_abnormal_return_pct"]) for item in items) / len(items),
            "source_signal_count": len(items),
        })
    return aggregated


class CalibratedImpactModel:
    """Persistable model returning both movement estimates and 1-10 scores."""
    def __init__(self, estimator: Pipeline, training_magnitudes: list[float]):
        self.estimator = estimator
        self.training_magnitudes = sorted(float(x) for x in training_magnitudes)

    def predict_magnitude(self, frame) -> np.ndarray:
        return np.maximum(0.0, np.expm1(self.estimator.predict(frame)))

    def predict(self, frame) -> np.ndarray:
        magnitudes = self.predict_magnitude(frame)
        scores = []
        for value in magnitudes:
            percentile = np.searchsorted(self.training_magnitudes, value, side="right") / len(self.training_magnitudes)
            scores.append(1.0 + 9.0 * min(1.0, max(0.0, float(percentile))))
        return np.asarray(scores, dtype=float)


def _make_model() -> Pipeline:
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    categorical = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("encode", OneHotEncoder(handle_unknown="ignore"))])
    prep = ColumnTransformer([("numeric", numeric, NUMERIC_FEATURES), ("categorical", categorical, CATEGORICAL_FEATURES)])
    return Pipeline([("features", prep), ("regressor", RandomForestRegressor(
        n_estimators=250, min_samples_leaf=8, max_features=0.9,
        random_state=42, n_jobs=-1
    ))])


def _frame(rows: list[dict[str, Any]]):
    import pandas as pd
    return pd.DataFrame([{key: row.get(key) for key in FEATURES} for row in rows], columns=FEATURES)


def fit_evaluate(rows: list[dict[str, Any]], *, test_fraction: float = 0.2) -> tuple[dict[str, Any], Pipeline, list[dict[str, Any]]]:
    """Train on earlier dates, evaluate on later dates, then fit deployable model."""
    observations = aggregate_correlated_events(rows)
    observations.sort(key=lambda row: row["event_date"])
    unique_dates = sorted({row["event_date"] for row in observations})
    if len(observations) < 50 or len(unique_dates) < 5:
        raise ValueError(f"Need at least 50 unique ticker/date observations across 5 dates; found {len(observations)} observations across {len(unique_dates)} dates")
    date_split = int(len(unique_dates) * (1.0 - test_fraction))
    date_split = min(max(date_split, 1), len(unique_dates) - 1)
    
    holdout_start = unique_dates[date_split]

    purge_days = 7
    training_cutoff = (
        date.fromisoformat(holdout_start) - timedelta(days=purge_days)
    ).isoformat()

    train = [
        row for row in observations
        if row["event_date"] < training_cutoff
    ]
    test = [
        row for row in observations
        if row["event_date"] >= holdout_start
    ]

    if len(train) < 50 or not test:
        raise ValueError("Insufficient observations after the purge split")

    X_train, X_test = _frame(train), _frame(test)
    y_train = np.log1p([row["target_abs_abnormal_return_pct"] for row in train])
    y_test = np.asarray([row["target_abs_abnormal_return_pct"] for row in test], dtype=float)
    eval_model = _make_model()
    eval_model.fit(X_train, y_train)
    predicted_log = eval_model.predict(X_test)
    predicted = np.maximum(0.0, np.expm1(predicted_log))
    baseline = np.asarray([row["impact"] for row in test], dtype=float)
    test_targets = y_test.tolist()
    baseline_corr = spearman(baseline.tolist(), test_targets)
    calibrated_corr = spearman(predicted.tolist(), test_targets)
    mae = float(mean_absolute_error(y_test, predicted))
    rmse = float(mean_squared_error(y_test, predicted) ** 0.5)
    # Convert the predicted return magnitude into a stable 1-10 score using only
    # the training target distribution. This avoids using held-out outcomes.
    train_magnitudes = np.expm1(y_train)
    def to_score(value: float) -> float:
        percentile = float(np.searchsorted(np.sort(train_magnitudes), value, side="right")) / len(train_magnitudes)
        return round(1.0 + 9.0 * min(1.0, max(0.0, percentile)), 4)
    for row, prediction in zip(test, predicted):
        row["predicted_abs_abnormal_return_pct"] = round(float(prediction), 6)
        row["calibrated_impact_score"] = to_score(float(prediction))
    metrics = {
        "observations_after_same_ticker_date_aggregation": len(observations),
        "training_observations": len(train),
        "holdout_observations": len(test),
        "purge_days": purge_days,
        "training_cutoff_exclusive": training_cutoff,
        "purged_observations": len(observations) - len(train) - len(test),
        "train_date_start": train[0]["event_date"],
        "train_date_end": train[-1]["event_date"],
        "holdout_date_start": test[0]["event_date"],
        "holdout_date_end": test[-1]["event_date"],
        "target": "absolute forward abnormal return (%)",
        "horizon_trading_days": None,
        "baseline_impact_spearman_holdout": round(baseline_corr, 6) if baseline_corr is not None else None,
        "predicted_magnitude_spearman_holdout": round(calibrated_corr, 6) if calibrated_corr is not None else None,
        "holdout_mae_percentage_points": round(mae, 6),
        "holdout_rmse_percentage_points": round(rmse, 6),
        "interpretation": "Chronological holdout association only; results are exploratory and not proof of predictive performance.",
    }
    deploy_estimator = _make_model()
    all_targets = [row["target_abs_abnormal_return_pct"] for row in observations]
    deploy_estimator.fit(_frame(observations), np.log1p(all_targets))
    deploy_model = CalibratedImpactModel(deploy_estimator, all_targets)
    return metrics, deploy_model, test


def score_signals(model_path: str | Path, input_csv: str | Path, output_csv: str | Path) -> int:
    """Score event-study rows with a previously fitted joblib model."""
    model = joblib.load(model_path)
    rows = load_event_rows(input_csv)
    if not rows:
        raise ValueError(f"No usable event rows found in {input_csv}")
    frame = _frame(rows)
    predictions = model.predict_magnitude(frame)
    scores = model.predict(frame)
    out = []
    for row, pred, score in zip(rows, predictions, scores):
        row["predicted_abs_abnormal_return_pct"] = round(float(pred), 6)
        row["calibrated_impact_score"] = round(float(score), 4)
        out.append(row)
    path = Path(output_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    return len(out)
