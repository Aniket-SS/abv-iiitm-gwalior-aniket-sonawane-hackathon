from pathlib import Path

import pytest

from src.modules.stress_test.engine import load_portfolio, load_scenarios, run_stress_test

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def portfolio():
    return load_portfolio(ROOT / "data/synthetic/wholesale_portfolio.csv")


@pytest.fixture
def scenarios():
    return load_scenarios(ROOT / "config/stress_scenarios.yaml")


def test_high_impact_market_signal_produces_before_after_valuation(portfolio, scenarios):
    signal = {"signal_id": "demo-1", "ticker": "MARKET", "scope": "market", "event_type": "geopolitical", "impact": 9.0}
    result = run_stress_test(signal, portfolio, scenarios)
    assert result["triggered"] is True
    assert result["scope"] == "market"
    assert result["portfolio_before_value"] > 0
    assert result["portfolio_after_value"] == round(result["portfolio_before_value"] + result["portfolio_pnl"], 2)
    assert len(result["assets"]) == len(portfolio)
    assert result["asset_class_breakdown"]
    assert {row["asset_type"] for row in result["asset_class_breakdown"]} >= {"loan", "bond", "derivative"}


def test_low_impact_signal_does_not_trigger():
    result = run_stress_test({"signal_id": "low", "event_type": "other", "impact": 4.0}, [], {"other": {"name": "fallback"}})
    assert result["triggered"] is False
    assert "below threshold" in result["reason"]


def test_company_signal_without_ticker_is_not_required_for_market_stress(portfolio, scenarios):
    signal = {"signal_id": "event-only", "ticker": None, "scope": "event", "event_type": "credit_event", "impact": 8.5}
    result = run_stress_test(signal, portfolio, scenarios)
    assert result["triggered"] is True
    assert result["ticker"] is None
    assert result["scope"] == "event"


def test_scenario_fallback_and_known_scenarios(scenarios):
    assert "other" in scenarios
    assert "geopolitical" in scenarios
    assert "credit_event" in scenarios


def test_asset_class_breakdown_reconciles_to_total(portfolio, scenarios):
    result = run_stress_test({"event_type": "geopolitical", "impact": 9, "scope": "market"}, portfolio, scenarios)
    assert round(sum(row["before_value"] for row in result["asset_class_breakdown"]), 2) == result["portfolio_before_value"]
    assert round(sum(row["pnl"] for row in result["asset_class_breakdown"]), 2) == result["portfolio_pnl"]
    assert round(sum(row["after_value"] for row in result["asset_class_breakdown"]), 2) == result["portfolio_after_value"]


@pytest.mark.parametrize("impact", [0, 10.1, float("nan")])
def test_invalid_impact_rejected(portfolio, scenarios, impact):
    with pytest.raises(ValueError, match="impact"):
        run_stress_test({"event_type": "other", "impact": impact}, portfolio, scenarios)
