from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


REQUIRED_PORTFOLIO_COLUMNS = {
    "asset_id", "asset_type", "name", "market_value", "notional",
    "rate_duration", "spread_duration", "equity_delta", "dv01",
    "vega_per_vol_point", "fx_delta",
}
SHOCK_SUFFIXES = ("_pct", "_bps", "_points")


def normalize_event_type(value: Any) -> str:
    """Normalize NLP labels to the keys used by stress_scenarios.yaml."""
    label = str(value or "other").strip().lower()
    label = label.replace("&", "and").replace("/", " ").replace("-", " ")
    label = "_".join(label.split())
    aliases = {
        "credit": "credit_event",
        "credit_event": "credit_event",
        "credit_events": "credit_event",
        "merger_and_acquisition": "merger_acquisition",
        "mergers_acquisitions": "merger_acquisition",
        "m_and_a": "merger_acquisition",
        "regulatory": "regulatory_legal",
        "legal": "regulatory_legal",
        "regulatory_or_legal_action": "regulatory_legal",
        "leadership": "leadership_change",
        "operational": "operational_disruption",
        "product": "product_launch",
        "macro_economic": "macroeconomic",
        "geo_political": "geopolitical",
    }
    return aliases.get(label, label)


def load_portfolio(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_PORTFOLIO_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Portfolio CSV missing columns: {sorted(missing)}")
        rows: list[dict[str, Any]] = []
        for line_number, raw in enumerate(reader, start=2):
            row: dict[str, Any] = {key: raw[key] for key in raw}
            for key in REQUIRED_PORTFOLIO_COLUMNS - {"asset_id", "asset_type", "name"}:
                try:
                    row[key] = float(row[key] or 0.0)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid numeric value for {key!r} on CSV line {line_number}") from exc
                if not math.isfinite(row[key]):
                    raise ValueError(f"Non-finite numeric value for {key!r} on CSV line {line_number}")
            row["asset_id"] = str(row["asset_id"]).strip()
            row["asset_type"] = str(row["asset_type"]).lower().strip()
            row["name"] = str(row["name"]).strip()
            if not row["asset_id"] or not row["asset_type"]:
                raise ValueError(f"asset_id and asset_type are required on CSV line {line_number}")
            if row["market_value"] < 0:
                raise ValueError(f"market_value cannot be negative on CSV line {line_number}")
            rows.append(row)
    if not rows:
        raise ValueError("Portfolio CSV contains no assets")
    if len({row["asset_id"] for row in rows}) != len(rows):
        raise ValueError("Portfolio CSV contains duplicate asset_id values")
    return rows


def load_scenarios(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream) or {}
    scenarios = config.get("scenarios", {})
    if not isinstance(scenarios, dict) or not scenarios or "other" not in scenarios:
        raise ValueError("Scenario YAML must define a non-empty 'scenarios' mapping with an 'other' fallback")
    for event_type, scenario in scenarios.items():
        if not isinstance(scenario, dict):
            raise ValueError(f"Scenario {event_type!r} must be a mapping")
        for key, value in scenario.items():
            if key.endswith(SHOCK_SUFFIXES):
                try:
                    number = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Scenario {event_type!r} has invalid shock {key!r}") from exc
                if not math.isfinite(number):
                    raise ValueError(f"Scenario {event_type!r} has non-finite shock {key!r}")
    return scenarios


def _asset_pnl(asset: dict[str, Any], shock: dict[str, float]) -> float:
    asset_type = str(asset["asset_type"]).lower()
    rate_bps = float(shock.get("rate_shock_bps", 0.0))
    spread_bps = float(shock.get("spread_shock_bps", 0.0))
    if asset_type in {"loan", "loans", "bond", "bonds"}:
        rate_pnl = -float(asset["market_value"]) * float(asset["rate_duration"]) * rate_bps / 10000.0
        spread_pnl = -float(asset["market_value"]) * float(asset["spread_duration"]) * spread_bps / 10000.0
        return rate_pnl + spread_pnl
    equity_pnl = float(asset["equity_delta"]) * float(shock.get("equity_shock_pct", 0.0)) / 100.0
    rate_pnl = -float(asset["dv01"]) * rate_bps
    vol_pnl = float(asset["vega_per_vol_point"]) * float(shock.get("vol_shock_points", 0.0))
    fx_pnl = float(asset["fx_delta"]) * float(shock.get("fx_shock_pct", 0.0)) / 100.0
    return equity_pnl + rate_pnl + vol_pnl + fx_pnl


def run_stress_test(
    signal: dict[str, Any],
    portfolio: list[dict[str, Any]],
    scenarios: dict[str, Any],
    *,
    impact_threshold: float = 7.0,
) -> dict[str, Any]:
    if not math.isfinite(float(impact_threshold)) or not 1 <= float(impact_threshold) <= 10:
        raise ValueError("impact_threshold must be between 1 and 10")
    try:
        impact = float(signal.get("impact", 0.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Signal impact must be numeric") from exc
    if not math.isfinite(impact) or not 1 <= impact <= 10:
        raise ValueError("Signal impact must be between 1 and 10")

    scope = str(signal.get("scope") or "company").strip().lower()
    if scope not in {"company", "event", "market"}:
        scope = "company"
    event_type = normalize_event_type(signal.get("event_type"))
    ticker = str(signal.get("ticker") or "").strip().upper() or None
    signal_id = signal.get("signal_id")
    base = {
        "triggered": False,
        "signal_id": signal_id,
        "timestamp": signal.get("timestamp"),
        "scope": scope,
        "ticker": ticker,
        "event_type": event_type,
        "impact": impact,
        "impact_threshold": float(impact_threshold),
    }
    if impact < impact_threshold:
        return {**base, "reason": f"Signal impact {impact:.2f} is below threshold {impact_threshold:.2f}"}
    if not portfolio:
        raise ValueError("Cannot run stress test with an empty portfolio")

    scenario_key = event_type if event_type in scenarios else "other"
    scenario = scenarios.get(scenario_key)
    if scenario is None:
        raise ValueError(f"No stress scenario configured for event type: {event_type}")
    shock = {key: float(value) for key, value in scenario.items() if key.endswith(SHOCK_SUFFIXES)}
    details = []
    before_total = 0.0
    pnl_total = 0.0
    class_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"before_value": 0.0, "pnl": 0.0, "after_value": 0.0, "assets": 0})
    for asset in portfolio:
        before = float(asset["market_value"])
        pnl = _asset_pnl(asset, shock)
        after = before + pnl
        if not math.isfinite(after):
            raise ValueError(f"Non-finite post-stress value for asset {asset.get('asset_id')}")
        asset_type = str(asset["asset_type"]).lower()
        before_total += before
        pnl_total += pnl
        class_totals[asset_type]["before_value"] += before
        class_totals[asset_type]["pnl"] += pnl
        class_totals[asset_type]["after_value"] += after
        class_totals[asset_type]["assets"] += 1
        details.append({
            "asset_id": asset["asset_id"],
            "asset_type": asset_type,
            "name": asset["name"],
            "before_value": round(before, 2),
            "pnl": round(pnl, 2),
            "after_value": round(after, 2),
            "pnl_pct_of_market_value": round(100.0 * pnl / before, 4) if before else None,
        })
    class_breakdown = []
    for asset_type, totals in sorted(class_totals.items()):
        class_breakdown.append({
            "asset_type": asset_type,
            "assets": int(totals["assets"]),
            "before_value": round(totals["before_value"], 2),
            "pnl": round(totals["pnl"], 2),
            "after_value": round(totals["after_value"], 2),
            "pnl_pct_of_portfolio_pnl": round(100.0 * totals["pnl"] / pnl_total, 2) if pnl_total else 0.0,
        })
    return {
        **base,
        "triggered": True,
        "scenario_key": scenario_key,
        "scenario_name": scenario.get("name", scenario_key.replace("_", " ").title()),
        "scenario_description": scenario.get("description", "Illustrative deterministic shock scenario"),
        "shocks": shock,
        "portfolio_before_value": round(before_total, 2),
        "portfolio_pnl": round(pnl_total, 2),
        "portfolio_after_value": round(before_total + pnl_total, 2),
        "portfolio_pnl_pct": round(100.0 * pnl_total / before_total, 4) if before_total else None,
        "asset_class_breakdown": class_breakdown,
        "assets": details,
        "assumptions": [
            "All values and sensitivities belong to a synthetic demonstration portfolio.",
            "Loan and bond P&L uses a linear duration approximation for rate and spread shocks.",
            "Derivative P&L uses the supplied delta, DV01, vega and FX sensitivities; convexity and nonlinear effects are omitted.",
            "The configured scenario is applied to the synthetic portfolio as a whole; company signals are not mapped to a specific real issuer exposure.",
        ],
        "disclaimer": "Synthetic portfolio and simplified sensitivities for demonstration; not a bank risk model or investment advice.",
    }
