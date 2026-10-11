from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.data_access import ROOT as PROJECT_ROOT, recent_signals
from src.modules.stress_test.engine import load_portfolio, load_scenarios, run_stress_test

st.set_page_config(page_title="Wholesale Portfolio Stress Tester", page_icon="🛡️", layout="wide")
st.title("🛡️ Module B — Wholesale Portfolio Stress Tester")
st.caption("Event-driven stress testing of a synthetic wholesale portfolio. All shocks and valuations are illustrative simulation assumptions.")

with st.sidebar:
    st.subheader("Stress configuration")
    threshold = st.slider("High-impact trigger threshold", 1.0, 10.0, 7.0, 0.5)
    lookback_days = st.selectbox("Signal recency", [30, 90, 180, 365], index=1, format_func=lambda value: f"Last {value} days")
    scope_filter = st.selectbox("Signal scope", ["all", "company", "event", "market"], format_func=lambda value: "All scopes" if value == "all" else value.title())
    portfolio_path = st.text_input("Portfolio CSV", str(PROJECT_ROOT / "data/synthetic/wholesale_portfolio.csv"))
    scenarios_path = st.text_input("Scenario YAML", str(PROJECT_ROOT / "config/stress_scenarios.yaml"))

try:
    portfolio = load_portfolio(portfolio_path)
    scenarios = load_scenarios(scenarios_path)
except Exception as exc:
    st.error(f"Could not load portfolio or scenarios: {exc}")
    st.stop()

signals = recent_signals(limit=5000, min_impact=threshold)
if not signals.empty:
    signals["timestamp"] = pd.to_datetime(signals["timestamp"], errors="coerce", utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_days)
    signals = signals[signals["timestamp"].ge(cutoff)].copy()
    if scope_filter != "all" and "scope" in signals.columns:
        signals = signals[signals["scope"].fillna("company").str.lower().eq(scope_filter)]
    signals = signals.sort_values("timestamp", ascending=False).reset_index(drop=True)

portfolio_value = sum(float(asset["market_value"]) for asset in portfolio)
asset_classes = sorted({str(asset["asset_type"]).lower() for asset in portfolio})
metric1, metric2, metric3 = st.columns(3)
metric1.metric("Synthetic portfolio value", f"${portfolio_value:,.0f}")
metric2.metric("Portfolio assets", len(portfolio))
metric3.metric("Asset classes", len(asset_classes))
st.caption("The evaluation datasets retained for later phases are not modified or used as live signals by this stress-test page.")

st.subheader("Select a high-impact signal")
if not signals.empty:
    labels = signals.apply(
        lambda row: f"{row['timestamp']} | {str(row.get('scope', 'company')).upper()} | {row.get('ticker') or 'NO TICKER'} | {row.get('event_type', 'other')} | impact {float(row.get('impact', 0)):.1f} | {row.get('signal_id', 'unknown')}",
        axis=1,
    ).tolist()
    selected_index = st.selectbox("Available signals", range(len(labels)), format_func=lambda index: labels[index])
    selected = signals.iloc[selected_index].to_dict()
    run_disabled = False
    st.caption(f"Showing {len(signals):,} signals matching impact ≥ {threshold:.1f}, scope and last {lookback_days} days.")
else:
    st.warning(f"No stored signal matches impact ≥ {threshold:.1f} in the last {lookback_days} days for the selected scope.")
    demo_event = st.selectbox("Synthetic demo event type", sorted(scenarios))
    use_demo = st.checkbox("I understand this is a synthetic demonstration, not a stored signal")
    selected = {
        "signal_id": "synthetic-demo-only",
        "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "ticker": None,
        "scope": "market",
        "event_type": demo_event,
        "impact": max(8.0, threshold),
    }
    run_disabled = not use_demo

if st.button("Run stress test", type="primary", disabled=run_disabled, use_container_width=True):
    try:
        result = run_stress_test(selected, portfolio, scenarios, impact_threshold=threshold)
    except Exception as exc:
        st.error(f"Stress test failed: {exc}")
        st.stop()

    if not result.get("triggered"):
        st.info(result.get("reason", "Stress test was not triggered."))
        st.stop()

    required = {"portfolio_before_value", "portfolio_pnl", "portfolio_after_value", "portfolio_pnl_pct", "assets"}
    missing = required - set(result)
    if missing:
        st.error(f"Stress-test engine returned an incomplete result. Missing fields: {', '.join(sorted(missing))}. Update the engine and dashboard together.")
        st.stop()

    st.divider()
    st.subheader("Stress-test results")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Before shock", f"${result['portfolio_before_value']:,.0f}")
    c2.metric("Stress P&L", f"${result['portfolio_pnl']:,.0f}", f"{result['portfolio_pnl_pct']:.2f}%")
    c3.metric("After shock", f"${result['portfolio_after_value']:,.0f}")
    c4.metric("Impact score", f"{float(result.get('impact', selected.get('impact', 0))):.1f}/10")

    st.markdown(f"**Scenario:** {result.get('scenario_name', result.get('event_type', 'Unknown'))}  \n{result.get('scenario_description', '')}")
    scope = str(result.get("scope") or selected.get("scope") or "event")
    ticker = result.get("ticker") or selected.get("ticker") or "Not applicable"
    try:
        result_threshold = float(result.get("impact_threshold", threshold))
    except (TypeError, ValueError):
        result_threshold = float(threshold)
    st.caption(f"Scope: {scope.title()} · Ticker: {ticker} · Threshold: {result_threshold:.1f}")

    assets = result.get("assets") or []
    asset_frame = pd.DataFrame(assets)
    required_asset_cols = {"name", "asset_type", "pnl"}
    if asset_frame.empty or not required_asset_cols.issubset(asset_frame.columns):
        st.error("The engine did not return valid asset-level valuations. Check the Phase 7 engine and dashboard versions.")
        st.stop()

    class_breakdown = result.get("asset_class_breakdown") or result.get("asset_type_breakdown") or []
    class_frame = pd.DataFrame(class_breakdown)
    if class_frame.empty:
        aggregations = {"assets": ("asset_type", "size"), "pnl": ("pnl", "sum")}
        if "before_value" in asset_frame.columns:
            aggregations["before_value"] = ("before_value", "sum")
        if "after_value" in asset_frame.columns:
            aggregations["after_value"] = ("after_value", "sum")
        class_frame = asset_frame.groupby("asset_type", dropna=False).agg(**aggregations).reset_index()

    left, right = st.columns(2)
    with left:
        if {"asset_type", "pnl"}.issubset(class_frame.columns):
            st.plotly_chart(px.bar(class_frame, x="asset_type", y="pnl", color="asset_type", title="P&L contribution by asset class", labels={"asset_type": "Asset class", "pnl": "Stress P&L ($)"}), use_container_width=True)
        else:
            st.warning("Asset-class breakdown has an unexpected structure.")
    with right:
        st.plotly_chart(px.bar(asset_frame, x="name", y="pnl", color="asset_type", title="P&L contribution by asset", labels={"name": "Portfolio asset", "pnl": "Stress P&L ($)"}), use_container_width=True)

    st.subheader("Configured shock assumptions")
    st.json(result.get("shocks") or {})
    st.subheader("Asset-level valuation")
    st.dataframe(asset_frame, use_container_width=True, hide_index=True)
    st.subheader("Asset-class reconciliation")
    st.dataframe(class_frame, use_container_width=True, hide_index=True)

    st.download_button("Download stress result JSON", json.dumps(result, indent=2, default=str, allow_nan=False), "stress_test_result.json", "application/json")
    st.caption(result.get("disclaimer", "Illustrative synthetic stress test; not an actual bank risk estimate."))
    with st.expander("Model assumptions and limitations"):
        for assumption in result.get("assumptions") or ["No assumptions were supplied by the engine."]:
            st.markdown(f"- {assumption}")
