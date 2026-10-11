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

from src.dashboard.data_access import ROOT as PROJECT_ROOT, qualifying_signals, signal_count
from src.modules.stress_test.engine import load_portfolio, load_scenarios, normalize_event_type, run_stress_test

st.set_page_config(page_title="Portfolio Stress Tester", page_icon="🛡️", layout="wide")
st.markdown("""<style>
.eyebrow{color:#7dd3fc;font-size:.78rem;font-weight:700;letter-spacing:.14em;margin-bottom:-.5rem}
[data-testid="stMetric"]{background:rgba(125,211,252,.06);border:1px solid rgba(148,163,184,.18);padding:14px 16px;border-radius:12px}
</style>""", unsafe_allow_html=True)
st.markdown("<div class='eyebrow'>MODULE B · EVENT-DRIVEN RISK</div>", unsafe_allow_html=True)
st.title("Wholesale Portfolio Stress Tester")
st.caption("Select an actual stored NLP risk signal, map its event classification to a configured scenario, and estimate the impact on a synthetic banking portfolio.")
st.info("**How to use:** Set the minimum impact and time window, optionally filter event type or scope, select a stored signal, and run the stress test. The portfolio is synthetic; the selected risk signal comes from the project database.")

PORTFOLIO_FILE = PROJECT_ROOT / "data" / "synthetic" / "wholesale_portfolio.csv"
SCENARIOS_FILE = PROJECT_ROOT / "config" / "stress_scenarios.yaml"

try:
    portfolio = load_portfolio(PORTFOLIO_FILE)
    scenarios = load_scenarios(SCENARIOS_FILE)
except Exception as exc:
    st.error("The synthetic portfolio or scenario configuration could not be loaded. Verify that the required project files are present.")
    st.exception(exc)
    st.stop()

scenario_options = sorted(scenarios.keys())
scenario_labels = {key: str(scenarios[key].get("name", key.replace("_", " ").title())) for key in scenario_options}
with st.sidebar:
    st.header("Event filters")
    threshold = st.slider("Minimum impact score", 1.0, 10.0, 7.0, 0.5, help="Only stored signals with impact at or above this score qualify. Example: 7.5 includes 7.5–10.")
    lookback_days = st.selectbox("Signal time window", [7, 30, 90, 180, 365, 3650], index=2, format_func=lambda value: "All available history" if value == 3650 else f"Last {value} days", help="Filters the database by timestamp. Use All available history to search the full retained timeline.")
    event_filter = st.selectbox("Event category", ["all", *scenario_options], format_func=lambda value: "All event categories" if value == "all" else scenario_labels[value])
    scope_filter = st.selectbox("Signal scope", ["all", "company", "event", "market"], format_func=lambda value: "All scopes" if value == "all" else value.title(), help="Company is issuer-specific; market is broad-market; event is event-level.")

query_days = 36500 if lookback_days == 3650 else lookback_days
signals = qualifying_signals(
    min_impact=threshold,
    since_days=query_days,
    scope=scope_filter,
    event_type=event_filter,
    display_limit=2000,
)

portfolio_value = sum(float(asset["market_value"]) for asset in portfolio)
asset_classes = sorted({str(asset["asset_type"]).lower() for asset in portfolio})
all_count = signal_count()
qualifying_count = len(signals)
metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("Synthetic portfolio value", f"${portfolio_value:,.0f}")
metric2.metric("Portfolio assets", f"{len(portfolio)}")
metric3.metric("Asset classes", f"{len(asset_classes)}")
metric4.metric("Signals in database", f"{all_count:,}")
st.caption("The portfolio values and sensitivities are illustrative. Only event signals are sourced from the stored NLP risk engine.")

st.subheader("1 · Select a qualifying stored event")
st.caption("The database is filtered in SQL using your criteria. The selector displays up to the 2,000 newest matches for usability; it does not use synthetic events.")
if signals.empty:
    st.warning(f"No stored signal matches impact ≥ {threshold:.1f}, the selected time window, event category and scope. Widen the time window or lower the impact threshold.")
    st.stop()

signals = signals.copy()
signals["timestamp"] = pd.to_datetime(signals["timestamp"], errors="coerce", utc=True)
signals["impact"] = pd.to_numeric(signals["impact"], errors="coerce")
signals["event_key"] = signals["event_type"].map(normalize_event_type)
labels = signals.apply(
    lambda row: (
        f"{row['timestamp'].strftime('%Y-%m-%d %H:%M UTC') if pd.notna(row['timestamp']) else 'Unknown time'}"
        f" · {str(row.get('event_type') or 'other').replace('_', ' ').title()}"
        f" · impact {float(row.get('impact') or 0):.1f}/10"
        f" · {str(row.get('ticker') or 'MARKET')}"
        f" · {str(row.get('signal_id') or '')[:10]}"
    ), axis=1
).tolist()
selected_index = st.selectbox("Stored risk signals", range(len(labels)), format_func=lambda index: labels[index])
selected = signals.iloc[selected_index].to_dict()
selected_event_key = normalize_event_type(selected.get("event_type"))
resolved_key = selected_event_key if selected_event_key in scenarios else "other"
resolved_scenario = scenarios[resolved_key]

if resolved_key != selected_event_key:
    st.warning(f"The stored event label '{selected.get('event_type')}' has no exact scenario mapping. The engine will use the explicit fallback scenario: {scenario_labels['other']}.")
else:
    st.success(f"Scenario mapping: **{scenario_labels[resolved_key]}**")

with st.expander("Preview the scenario before running"):
    st.write(resolved_scenario.get("description", "Configured illustrative shock scenario."))
    preview_shocks = {key: value for key, value in resolved_scenario.items() if key.endswith(("_pct", "_bps", "_points"))}
    st.json(preview_shocks)

st.caption(f"Showing {len(signals):,} matching signal(s) in the selector. Total stored signals in database: {all_count:,}.")
if st.button("Run portfolio stress test", type="primary", use_container_width=True):
    try:
        result = run_stress_test(selected, portfolio, scenarios, impact_threshold=threshold)
    except Exception as exc:
        st.error(f"Stress test failed: {exc}")
        st.stop()
    if not result.get("triggered"):
        st.info(result.get("reason", "The selected event did not trigger a stress test."))
        st.stop()

    st.divider()
    st.subheader("2 · Stress-test result")
    before = float(result["portfolio_before_value"])
    pnl = float(result["portfolio_pnl"])
    after = float(result["portfolio_after_value"])
    pnl_pct = float(result.get("portfolio_pnl_pct") or 0.0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Before shock", f"${before:,.0f}")
    c2.metric("Simulated P&L", f"${pnl:,.0f}", f"{pnl_pct:+.2f}%")
    c3.metric("After shock", f"${after:,.0f}")
    c4.metric("Event impact", f"{float(result.get('impact', selected.get('impact', 0))):.1f}/10")
    st.markdown(f"### {result.get('scenario_name', scenario_labels.get(resolved_key, resolved_key))}")
    st.write(result.get("scenario_description", "Configured illustrative scenario."))
    st.caption(f"Original event label: {selected.get('event_type', 'other')} · Resolved scenario key: `{result.get('scenario_key', resolved_key)}` · Scope: {str(result.get('scope') or selected.get('scope') or 'event').title()} · Trigger: impact ≥ {threshold:.1f}/10")

    asset_frame = pd.DataFrame(result.get("assets") or [])
    class_frame = pd.DataFrame(result.get("asset_class_breakdown") or [])
    if asset_frame.empty or not {"name", "asset_type", "pnl"}.issubset(asset_frame.columns):
        st.error("The stress-test engine did not return valid asset-level results.")
        st.stop()
    if class_frame.empty:
        class_frame = asset_frame.groupby("asset_type", dropna=False).agg(assets=("asset_type", "size"), pnl=("pnl", "sum")).reset_index()

    left, right = st.columns(2)
    with left:
        fig_class = px.bar(class_frame, x="asset_type", y="pnl", color="asset_type", text_auto=".3s", title="Simulated P&L by asset class", labels={"asset_type": "Asset class", "pnl": "P&L ($)"})
        fig_class.update_layout(template="plotly_dark", showlegend=False, xaxis_title="Asset class", yaxis_title="P&L ($)")
        st.plotly_chart(fig_class, use_container_width=True)
    with right:
        asset_plot = asset_frame.sort_values("pnl")
        fig_asset = px.bar(asset_plot, x="pnl", y="name", color="asset_type", orientation="h", text_auto=".3s", title="Simulated P&L by asset", labels={"name": "Portfolio asset", "pnl": "P&L ($)"})
        fig_asset.update_layout(template="plotly_dark", xaxis_title="P&L ($)", yaxis_title=None)
        st.plotly_chart(fig_asset, use_container_width=True)

    st.subheader("3 · Portfolio valuation before and after the shock")
    value_frame = pd.DataFrame({"Stage": ["Before shock", "After shock"], "Portfolio value ($)": [before, after]})
    fig_value = px.bar(value_frame, x="Stage", y="Portfolio value ($)", text_auto=".3s", title=f"Valuation impact · {result.get('scenario_name', resolved_key)}")
    fig_value.update_layout(template="plotly_dark", yaxis_title="Portfolio value ($)", xaxis_title=None)
    st.plotly_chart(fig_value, use_container_width=True)
    st.subheader("Applied shocks")
    shock_frame = pd.DataFrame([{"Parameter": key.replace("_", " ").title(), "Applied value": value} for key, value in (result.get("shocks") or {}).items()])
    st.dataframe(shock_frame, use_container_width=True, hide_index=True)
    st.subheader("Asset-level valuation details")
    display_columns = [column for column in ["asset_id", "name", "asset_type", "before_value", "pnl", "after_value", "pnl_pct_of_market_value"] if column in asset_frame.columns]
    st.dataframe(asset_frame[display_columns], use_container_width=True, hide_index=True)
    st.download_button("Download stress-test result (JSON)", json.dumps(result, indent=2, default=str, allow_nan=False), "stress_test_result.json", "application/json")
    with st.expander("Model assumptions and limitations"):
        for assumption in result.get("assumptions") or []:
            st.markdown(f"- {assumption}")
        st.caption(result.get("disclaimer", "Synthetic portfolio stress test; not a bank risk model or investment advice."))
