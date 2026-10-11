from datetime import date, timedelta
import csv
from pathlib import Path
import pytest
from src.market.calibration import event_study
from src.market.learned_impact import aggregate_correlated_events, load_event_rows


def test_event_study_uses_first_trading_day_after_event_date():
    prices = {
        "AAA": {date(2024, 1, 2): 100.0, date(2024, 1, 3): 110.0, date(2024, 1, 4): 121.0, date(2024, 1, 5): 120.0},
        "SPY": {date(2024, 1, 2): 100.0, date(2024, 1, 3): 100.0, date(2024, 1, 4): 100.0, date(2024, 1, 5): 100.0},
    }
    rows = event_study([{"signal_id":"x", "timestamp":"2024-01-03T20:00:00+00:00", "ticker":"AAA", "scope":"company", "impact":5, "confidence":0.8, "sentiment":0.5}], prices, horizons=(1,))
    assert rows[0]["matched_price_date"] == "2024-01-04"
    assert rows[0]["forward_return_pct_1d"] == pytest.approx((120/121-1)*100)


def test_aggregate_same_ticker_day_reduces_duplicate_rows():
    base = {"event_date":"2024-01-02", "ticker":"AAPL", "impact":4.0, "confidence":0.6, "abs_sentiment":0.2, "event_type":"earnings", "channel":"news", "scope":"company", "target_abs_abnormal_return_pct":2.0}
    rows = aggregate_correlated_events([base, {**base, "impact":8.0, "confidence":0.8, "target_abs_abnormal_return_pct":4.0}])
    assert len(rows) == 1
    assert rows[0]["impact"] == 8.0
    assert rows[0]["source_signal_count"] == 2
    assert rows[0]["target_abs_abnormal_return_pct"] == 3.0


def test_load_event_rows_skips_missing_target(tmp_path: Path):
    path = tmp_path / "events.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["event_date", "impact", "confidence", "sentiment", "abnormal_return_pct_3d", "ticker", "event_type", "channel", "scope"])
        writer.writeheader()
        writer.writerow({"event_date":"2024-01-02", "impact":5, "confidence":0.8, "sentiment":0.4, "abnormal_return_pct_3d":-2.5, "ticker":"AAPL", "event_type":"earnings", "channel":"news", "scope":"company"})
        writer.writerow({"event_date":"2024-01-03", "impact":5, "confidence":0.8, "sentiment":0.4, "abnormal_return_pct_3d":"", "ticker":"AAPL", "event_type":"earnings", "channel":"news", "scope":"company"})
    rows = load_event_rows(path)
    assert len(rows) == 1
    assert rows[0]["target_abs_abnormal_return_pct"] == 2.5


def test_fit_evaluate_uses_chronological_holdout_and_returns_scores():
    from src.market.learned_impact import fit_evaluate
    rows = []
    start = date(2023, 1, 1)
    for day_idx in range(80):
        for ticker_idx, ticker in enumerate(("AAPL", "MSFT")):
            impact = float(1 + ((day_idx + ticker_idx) % 10))
            magnitude = float(0.2 + impact * 0.15 + ((day_idx * 7 + ticker_idx) % 5) * 0.03)
            rows.append({
                "event_date": (start + timedelta(days=day_idx)).isoformat(),
                "ticker": ticker,
                "impact": impact,
                "confidence": 0.5 + (impact / 20),
                "abs_sentiment": min(1.0, impact / 10),
                "event_type": "earnings" if ticker_idx == 0 else "other",
                "channel": "news",
                "scope": "company",
                "target_abs_abnormal_return_pct": magnitude,
            })
    metrics, model, holdout = fit_evaluate(rows)
    assert metrics["train_date_end"] < metrics["holdout_date_start"]
    assert metrics["holdout_observations"] == len(holdout)
    assert all(1 <= row["calibrated_impact_score"] <= 10 for row in holdout)
    frame = __import__("src.market.learned_impact", fromlist=["_frame"])._frame(holdout[:3])
    assert len(model.predict(frame)) == 3
    assert len(model.predict_magnitude(frame)) == 3
