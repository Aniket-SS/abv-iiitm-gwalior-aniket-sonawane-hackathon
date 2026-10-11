from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.data_access import database_path, price_path
from src.modules.rebalancer.engine import (
    MOCK_INDEX_TICKERS,
    add_spy_benchmark,
    backtest_rebalancer,
    load_price_panel,
    load_signals_from_db,
    performance_summary,
)

st.set_page_config(page_title="Sentiment Index Rebalancer", page_icon="📈", layout="wide")

st.title("📈 Tactical Index Rebalancer")
st.caption("Module A · Historical simulation · 16-stock mock index · SPY benchmark")
st.info(
    "**Timing convention:** a signal published during a trading date is not used to earn that same date's return. "
    "The weights shown for a date are the allocation calculated for the next return period. Results exclude transaction costs."
)


@st.cache_data(ttl=300, show_spinner="Rebuilding historical backtest…")
def calculate_backtest(prices_file, db_file, lookback, confidence, tilt, max_weight, turnover, prices_mtime, db_mtime):
    all_prices = load_price_panel(prices_file)
    missing = sorted(set(MOCK_INDEX_TICKERS) - set(all_prices.columns))
    if missing:
        raise ValueError(f"Mock index tickers missing from price data: {missing}")
    prices = all_prices[MOCK_INDEX_TICKERS].copy()
    spy_prices = all_prices["SPY"].copy() if "SPY" in all_prices.columns else None
    signals = load_signals_from_db(db_file)
    weights, daily = backtest_rebalancer(
        prices,
        signals,
        lookback_days=lookback,
        min_confidence=confidence,
        max_tilt=tilt,
        max_weight=max_weight,
        turnover_limit=turnover,
    )
    if spy_prices is not None:
        daily = add_spy_benchmark(daily, spy_prices, prices.index)
    return weights, daily, len(prices.columns), len(prices), signals


with st.sidebar:
    st.header("Backtest controls")
    st.caption("Changing a control recalculates the historical simulation.")
    refresh = st.button("↻ Refresh data and signals", use_container_width=True)
    if refresh:
        st.cache_data.clear()
        st.rerun()
    lookback = st.slider("Signal lookback (calendar days)", 1, 30, 7)
    confidence = st.slider("Minimum signal confidence", 0.0, 1.0, 0.50, 0.05)
    tilt = st.slider("Maximum sentiment tilt", 0.0, 1.0, 0.50, 0.05)
    max_weight = st.slider("Maximum weight per stock", 0.05, 0.50, 0.15, 0.01)
    turnover = st.slider("Maximum one-way turnover per rebalance", 0.01, 0.50, 0.10, 0.01)
    chart_window = st.selectbox(
        "Chart time range", [3, 6, 12, 24, 0], index=2,
        format_func=lambda months: "Full history" if months == 0 else f"Last {months} months",
    )
    st.divider()
    st.caption("SPY is benchmark-only and is not included in the 16-stock mock index.")

price_file = price_path()
db_file = database_path()
if not price_file.exists():
    st.error(f"Price data not found: {price_file}")
    st.stop()
if not db_file.exists():
    st.error(f"Signal database not found: {db_file}")
    st.stop()

try:
    weights, daily, universe_count, date_count, signals = calculate_backtest(
        str(price_file),
        str(db_file),
        lookback,
        confidence,
        tilt,
        max_weight,
        turnover,
        price_file.stat().st_mtime,
        db_file.stat().st_mtime,
    )
except Exception as exc:
    st.error(f"Backtest could not run: {exc}")
    st.stop()

summary = performance_summary(daily)
weights["date"] = pd.to_datetime(weights["date"])
daily["date"] = pd.to_datetime(daily["date"])
if chart_window:
    chart_cutoff = daily["date"].max() - pd.DateOffset(months=int(chart_window))
    chart_daily = daily[daily["date"] >= chart_cutoff].copy()
    chart_weights = weights[weights["date"] >= chart_cutoff].copy()
else:
    chart_daily = daily.copy()
    chart_weights = weights.copy()
weights["equal_weight_baseline"] = 1.0 / universe_count
weights["active_weight"] = weights["weight"] - weights["equal_weight_baseline"]
weights["weight_pct"] = weights["weight"] * 100
weights["signal_sentiment"] = pd.to_numeric(weights["signal_sentiment"], errors="coerce").fillna(0.0)

eligible_signals = signals[
    signals["ticker"].isin(MOCK_INDEX_TICKERS) & (signals["confidence"] >= confidence)
].copy()
if not eligible_signals.empty:
    eligible_signals["signal_date"] = eligible_signals["timestamp"].dt.date
    first_signal_date = eligible_signals["signal_date"].min()
    last_signal_date = eligible_signals["signal_date"].max()
    active_tickers = int(eligible_signals["ticker"].nunique())
else:
    first_signal_date = last_signal_date = None
    active_tickers = 0

# Top-line cards
cards = st.columns(5)
cards[0].metric("Mock index stocks", f"{universe_count}")
cards[1].metric("Price dates", f"{date_count:,}")
cards[2].metric("Sentiment strategy", f"{summary['strategy_cumulative_return']:.2%}")
cards[3].metric("Equal-weight portfolio", f"{summary['equal_weight_cumulative_return']:.2%}")
if "spy_cumulative_return" in summary:
    cards[4].metric("SPY buy-and-hold", f"{summary['spy_cumulative_return']:.2%}")
else:
    cards[4].metric("SPY benchmark", "Unavailable")

with st.expander("Signal coverage and assumptions", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company signals loaded", f"{len(signals):,}")
    c2.metric("Eligible signals", f"{len(eligible_signals):,}")
    c3.metric("Tickers with eligible signals", f"{active_tickers}/16")
    c4.metric("Signal date coverage", f"{first_signal_date or '—'} → {last_signal_date or '—'}")
    st.write(
        "A ticker can remain at its equal-weight baseline when it has no eligible signal in the lookback window. "
        "Weight changes are also constrained by the maximum single-stock weight and turnover cap."
    )

st.subheader("Portfolio performance")
value_columns = ["strategy_value", "equal_weight_value"]
if "spy_value" in daily.columns:
    value_columns.append("spy_value")
chart_daily = chart_daily.copy()
for value_column in value_columns:
    first_value = float(chart_daily[value_column].iloc[0]) if not chart_daily.empty else 0.0
    if first_value:
        chart_daily[value_column] = chart_daily[value_column] / first_value
chart_data = chart_daily.melt(id_vars="date", value_vars=value_columns, var_name="portfolio", value_name="growth_of_1")
chart_data["portfolio"] = chart_data["portfolio"].map({
    "strategy_value": "Sentiment tilted",
    "equal_weight_value": "Static equal weight",
    "spy_value": "SPY buy-and-hold",
})
fig = px.line(chart_data, x="date", y="growth_of_1", color="portfolio")
fig.update_layout(
    template="plotly_dark",
    height=420,
    margin=dict(l=10, r=10, t=20, b=10),
    legend_title_text="Portfolio",
    xaxis_title="Date",
    yaxis_title="Growth of 1 unit of capital",
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

stats_rows = [
    {"Metric": "Cumulative return", "Sentiment tilted": summary["strategy_cumulative_return"], "Equal weight": summary["equal_weight_cumulative_return"]},
    {"Metric": "Annualized volatility", "Sentiment tilted": summary["strategy_annualized_volatility"], "Equal weight": summary["equal_weight_annualized_volatility"]},
    {"Metric": "Sharpe ratio (zero risk-free rate)", "Sentiment tilted": summary["strategy_sharpe_zero_rf"], "Equal weight": summary["equal_weight_sharpe_zero_rf"]},
    {"Metric": "Maximum drawdown", "Sentiment tilted": summary["strategy_max_drawdown"], "Equal weight": summary["equal_weight_max_drawdown"]},
]
if "spy_cumulative_return" in summary:
    for label, key in [
        ("Cumulative return", "cumulative_return"),
        ("Annualized volatility", "annualized_volatility"),
        ("Sharpe ratio (zero risk-free rate)", "sharpe_zero_rf"),
        ("Maximum drawdown", "max_drawdown"),
    ]:
        stats_rows.append({"Metric": f"SPY — {label}", "Sentiment tilted": None, "Equal weight": None, "SPY": summary[f"spy_{key}"]})
st.dataframe(pd.DataFrame(stats_rows), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Allocation over time")
st.caption("Use the date slider below to inspect a specific allocation. The heatmap is sampled weekly for readability; downloaded data remains daily.")
heatmap_weights = chart_weights.pivot(index="ticker", columns="date", values="weight").sort_index()
heatmap_sample = heatmap_weights.iloc[:, ::5]
fig_heat = go.Figure(data=go.Heatmap(
    z=heatmap_sample.to_numpy(),
    x=heatmap_sample.columns,
    y=heatmap_sample.index,
    colorscale="Blues",
    colorbar=dict(title="Weight", tickformat=".1%"),
    zmin=max(0, float(weights["weight"].quantile(0.02))),
    zmax=float(weights["weight"].quantile(0.98)),
    hovertemplate="Date: %{x|%Y-%m-%d}<br>Ticker: %{y}<br>Weight: %{z:.2%}<extra></extra>",
))
fig_heat.update_layout(template="plotly_dark", height=520, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="Date", yaxis_title="Ticker")
st.plotly_chart(fig_heat, use_container_width=True)

all_dates = sorted(chart_weights["date"].unique())
selected_date = st.select_slider(
    "Inspect allocation date",
    options=all_dates,
    value=all_dates[-1],
    format_func=lambda value: pd.Timestamp(value).strftime("%Y-%m-%d"),
)
selected = chart_weights[chart_weights["date"] == selected_date].copy().sort_values("weight", ascending=False)
selected_ticker = st.selectbox("Inspect stock", MOCK_INDEX_TICKERS, index=0)
row = selected[selected["ticker"] == selected_ticker].iloc[0]
base = float(row["equal_weight_baseline"])
actual = float(row["weight"])
sentiment = float(row["signal_sentiment"])
active = actual - base

st.markdown("#### Allocation audit")
a1, a2, a3, a4 = st.columns(4)
a1.metric(f"{selected_ticker} weight", f"{actual:.2%}", f"{active:+.2%} vs equal weight")
a2.metric("Equal-weight baseline", f"{base:.2%}")
a3.metric("Aggregated sentiment", f"{sentiment:+.3f}", help="Confidence-weighted, time-decayed sentiment in the configured lookback window.")
if sentiment > 0 and active > 0:
    verdict = "Positive sentiment / above baseline"
elif sentiment < 0 and active < 0:
    verdict = "Negative sentiment / below baseline"
elif abs(sentiment) < 1e-9 and abs(active) < 1e-6:
    verdict = "Neutral / at baseline"
else:
    verdict = "Constrained or relative allocation — inspect below"
a4.metric("Direction check", verdict)

if sentiment > 0 and active <= 1e-6:
    st.warning("Positive sentiment is not above the equal-weight baseline on this date. Other stocks' signals, the weight cap, and turnover constraints can affect the final allocation. Inspect the time series before treating this as a directional failure.")
elif sentiment < 0 and active >= -1e-6:
    st.warning("Negative sentiment is not below the equal-weight baseline on this date. Other stocks' signals, the weight cap, and turnover constraints can affect the final allocation. Inspect the time series before treating this as a directional failure.")

fig_bar = px.bar(
    selected.sort_values("weight"),
    x="weight",
    y="ticker",
    orientation="h",
    title=f"Portfolio weights on {pd.Timestamp(selected_date).strftime('%Y-%m-%d')}",
    labels={"weight": "Portfolio weight", "ticker": "Stock"},
)
fig_bar.add_vline(x=base, line_dash="dash", line_color="#F59E0B", annotation_text=f"Equal weight {base:.2%}")
fig_bar.update_layout(template="plotly_dark", height=520, margin=dict(l=10, r=10, t=45, b=10), xaxis_tickformat=".1%")
st.plotly_chart(fig_bar, use_container_width=True)

selected_ticker_history = chart_weights[chart_weights["ticker"] == selected_ticker].sort_values("date")
fig_ticker = go.Figure()
fig_ticker.add_trace(go.Scatter(x=selected_ticker_history["date"], y=selected_ticker_history["weight"], mode="lines", name=f"{selected_ticker} weight"))
fig_ticker.add_hline(y=base, line_dash="dash", line_color="#F59E0B", annotation_text=f"Equal weight {base:.2%}")
fig_ticker.update_layout(template="plotly_dark", height=320, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="Date", yaxis_title="Weight", yaxis_tickformat=".1%")
st.plotly_chart(fig_ticker, use_container_width=True)

st.subheader("Daily allocation table")
show = selected[["ticker", "weight", "equal_weight_baseline", "active_weight", "signal_sentiment"]].copy()
show = show.rename(columns={"ticker": "Ticker", "weight": "Weight", "equal_weight_baseline": "Equal weight", "active_weight": "Difference", "signal_sentiment": "Sentiment"})
st.dataframe(show.style.format({"Weight": "{:.2%}", "Equal weight": "{:.2%}", "Difference": "{:+.2%}", "Sentiment": "{:+.3f}"}), use_container_width=True, hide_index=True)

st.download_button("⬇ Download daily weights", weights.to_csv(index=False).encode("utf-8"), "weights_over_time.csv", "text/csv")
st.download_button("⬇ Download performance series", daily.to_csv(index=False).encode("utf-8"), "performance_comparison.csv", "text/csv")
st.caption(f"Charts show: {'full history' if chart_window == 0 else f'last {chart_window} months'}. CSV downloads retain the full backtest. Eligible signal rows: {len(eligible_signals):,} · Signal-bearing tickers: {active_tickers}/16 · Turnover cap: {turnover:.0%} per rebalance · Transaction costs excluded.")
