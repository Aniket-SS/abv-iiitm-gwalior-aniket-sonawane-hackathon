
import importlib

from fastapi.testclient import TestClient

api_module = importlib.import_module("src.api.app")


class FakeImpactModel:
    def predict_magnitude(self, frame):
        assert list(frame.columns) == [
            "impact",
            "confidence",
            "abs_sentiment",
            "event_type",
            "channel",
            "scope",
            "ticker",
        ]
        return [2.4]

    def predict(self, frame):
        return [6.5]


class FakeStore:
    def get(self, signal_id):
        return {
            "signal_id": signal_id,
            "impact": 4.0,
            "confidence": 0.8,
            "sentiment": -0.6,
            "event_type": "other",
            "channel": "news",
            "scope": "company",
            "ticker": "META",
        }


def test_impact_calibration_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "get_impact_model",
        lambda: FakeImpactModel(),
    )

    api_module.app.dependency_overrides[api_module.get_store] = (
        lambda: FakeStore()
    )

    try:
        with TestClient(api_module.app) as client:
            response = client.get(
                "/signals/test-id/impact-calibration"
            )
    finally:
        api_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["original_impact"] == 4.0
    assert body["predicted_abs_abnormal_return_pct"] == 2.4
    assert body["calibrated_impact_score"] == 6.5
    assert body["experimental"] is True
