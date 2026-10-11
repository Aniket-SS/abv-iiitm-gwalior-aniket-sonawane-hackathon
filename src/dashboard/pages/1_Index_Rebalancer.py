from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

st.set_page_config(
    page_title="Sentiment Index Rebalancer",
    page_icon="📈",
    layout="wide",
)

st.markdown("<div class='eyebrow'>MODULE A · MARKET SIGNALS</div>", unsafe_allow_html=True)
st.title("📈 Tactical Index Rebalancer")
st.caption("Historical simulation of a 16-stock mock index, with SPY shown only as a benchmark.")
st.markdown("""<style>
.eyebrow{color:#7dd3fc;font-size:.78rem;font-weight:700;letter-spacing:.14em;margin-bottom:-.5rem}
[data-testid="stMetric"]{background:rgba(125,211,252,.06);border:1px solid rgba(148,163,184,.18);padding:14px 16px;border-radius:12px}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{font-size:.92rem}
</style>""", unsafe_allow_html=True)
st.info(
    "**Timing convention:** a signal published during a trading date is not used "
    "to earn that same date's return. The weights shown for a date are the "
    "allocation calculated for the next return period. Results exclude transaction costs."
)


@st.cache_data(ttl=300, show_spinner="Rebuilding historical backtest…")
def calculate_backtest(
    prices_file,
    db_file,
    lookback,
    confidence,
    tilt,
    max_weight,
    turnover,
    prices_mtime,
    db_mtime,
):
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

    if weights.empty:
        raise ValueError("The backtest returned no allocation rows.")
    if daily.empty:
        raise ValueError("The backtest returned no performance rows.")

    if spy_prices is not None:
        daily = add_spy_benchmark(daily, spy_prices, prices.index)

    return weights, daily, len(prices.columns), len(prices), signals


with st.sidebar:
    st.header("Backtest controls")
    st.caption("These settings change the historical simulation, not live trading orders.")

    if st.button("↻ Refresh data and signals", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    lookback = st.slider("Signal lookback window", 1, 30, 7, help="How many calendar days of signals are considered for each stock. Shorter windows react faster; longer windows smooth noise.")
    confidence = st.slider("Minimum confidence", 0.0, 1.0, 0.50, 0.05, help="Signals below this confidence are ignored. 0.50 means only signals with at least 50% confidence qualify.")
    tilt = st.slider("Sentiment influence", 0.0, 1.0, 0.50, 0.05, help="Controls how strongly sentiment moves target weights away from equal weight. 0 disables sentiment tilting.")
    max_weight = st.slider("Maximum allocation per stock", 0.05, 0.50, 0.15, 0.01, help="Hard cap for any one stock. The value must be large enough for all 16 stocks to sum to 100%.")
    turnover = st.slider(
        "Maximum turnover per rebalance", 0.01, 0.50, 0.10, 0.01, help="Limits how much the portfolio can change at each rebalance. Lower values reduce trading but make weights adjust more slowly."
    )
    chart_window = st.selectbox(
        "History shown in charts",
        [3, 6, 12, 24, 0],
        index=2,
        format_func=lambda months: (
            "Full history" if months == 0 else f"Last {months} months"
        ),
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

required_weight_columns = {"date", "ticker", "weight"}
missing_weight_columns = required_weight_columns - set(weights.columns)
if missing_weight_columns:
    st.error(
        "The rebalancer returned an unexpected weights schema. Missing columns: "
        f"{sorted(missing_weight_columns)}"
    )
    st.stop()

if "signal_sentiment" not in weights.columns:
    weights["signal_sentiment"] = 0.0

weights["date"] = pd.to_datetime(weights["date"], errors="coerce")
daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
weights["weight"] = pd.to_numeric(weights["weight"], errors="coerce").fillna(0.0)
weights["signal_sentiment"] = pd.to_numeric(
    weights["signal_sentiment"], errors="coerce"
).fillna(0.0)
weights = weights.dropna(subset=["date", "ticker"]).copy()
daily = daily.dropna(subset=["date"]).copy()

if weights.empty or daily.empty:
    st.error("No valid dates or allocations are available to display.")
    st.stop()

# Add these columns before creating chart_weights so every view uses the same schema.
weights["equal_weight_baseline"] = 1.0 / max(1, universe_count)
weights["active_weight"] = weights["weight"] - weights["equal_weight_baseline"]
weights["weight_pct"] = weights["weight"] * 100.0

summary = performance_summary(daily)

if chart_window:
    chart_cutoff = daily["date"].max() - pd.DateOffset(months=int(chart_window))
    chart_daily = daily[daily["date"] >= chart_cutoff].copy()
    chart_weights = weights[weights["date"] >= chart_cutoff].copy()
else:
    chart_daily = daily.copy()
    chart_weights = weights.copy()

if chart_daily.empty:
    chart_daily = daily.copy()
if chart_weights.empty:
    chart_weights = weights.copy()

if signals.empty:
    eligible_signals = signals.copy()
else:
    signals = signals.copy()
    if "timestamp" in signals.columns:
        signals["timestamp"] = pd.to_datetime(signals["timestamp"], errors="coerce")
    if "ticker" not in signals.columns:
        signals["ticker"] = ""
    if "confidence" not in signals.columns:
        signals["confidence"] = 0.0
    signals["confidence"] = pd.to_numeric(
        signals["confidence"], errors="coerce"
    ).fillna(0.0)
    eligible_signals = signals[
        signals["ticker"].isin(MOCK_INDEX_TICKERS)
        & (signals["confidence"] >= confidence)
    ].copy()

if (
    not eligible_signals.empty
    and "timestamp" in eligible_signals.columns
    and eligible_signals["timestamp"].notna().any()
):
    eligible_signals["signal_date"] = eligible_signals["timestamp"].dt.date
    first_signal_date = eligible_signals["signal_date"].min()
    last_signal_date = eligible_signals["signal_date"].max()
    active_tickers = int(eligible_signals["ticker"].nunique())
else:
    first_signal_date = last_signal_date = None
    active_tickers = 0

cards = st.columns(5)
cards[0].metric("Mock index stocks", f"{universe_count}")
cards[1].metric("Price dates", f"{date_count:,}")
cards[2].metric(
    "Sentiment strategy", f"{summary['strategy_cumulative_return']:.2%}"
)
cards[3].metric(
    "Equal-weight portfolio", f"{summary['equal_weight_cumulative_return']:.2%}"
)
if "spy_cumulative_return" in summary:
    cards[4].metric("SPY buy-and-hold", f"{summary['spy_cumulative_return']:.2%}")
else:
    cards[4].metric("SPY benchmark", "Unavailable")

with st.expander("Signal coverage and assumptions", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company signals loaded", f"{len(signals):,}")
    c2.metric("Eligible signals", f"{len(eligible_signals):,}")
    c3.metric("Tickers with eligible signals", f"{active_tickers}/{universe_count}")
    c4.metric(
        "Signal date coverage",
        f"{first_signal_date or '—'} → {last_signal_date or '—'}",
    )
    st.write(
        "A ticker can remain at its equal-weight baseline when it has no eligible "
        "signal in the lookback window. Weight changes are also constrained by "
        "the maximum single-stock weight and turnover cap."
    )

st.subheader("Portfolio performance")
st.caption("Cumulative growth of one unit of starting capital. Past simulated performance does not imply future results.")
value_columns = ["strategy_value", "equal_weight_value"]
if "spy_value" in daily.columns:
    value_columns.append("spy_value")

missing_value_columns = [column for column in value_columns if column not in chart_daily]
if missing_value_columns:
    st.error(f"Performance data is missing columns: {missing_value_columns}")
    st.stop()

chart_daily = chart_daily.copy()
for value_column in value_columns:
    first_value = (
        float(chart_daily[value_column].iloc[0]) if not chart_daily.empty else 0.0
    )
    if first_value and pd.notna(first_value):
        chart_daily[value_column] = chart_daily[value_column] / first_value

chart_data = chart_daily.melt(
    id_vars="date",
    value_vars=value_columns,
    var_name="portfolio",
    value_name="growth_of_1",
)
chart_data["portfolio"] = chart_data["portfolio"].map(
    {
        "strategy_value": "Sentiment tilted",
        "equal_weight_value": "Static equal weight",
        "spy_value": "SPY buy-and-hold",
    }
)

fig = px.line(
    chart_data, x="date", y="growth_of_1", color="portfolio"
)
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
    {
        "Metric": "Cumulative return",
        "Sentiment tilted": summary["strategy_cumulative_return"],
        "Equal weight": summary["equal_weight_cumulative_return"],
    },
    {
        "Metric": "Annualized volatility",
        "Sentiment tilted": summary["strategy_annualized_volatility"],
        "Equal weight": summary["equal_weight_annualized_volatility"],
    },
    {
        "Metric": "Sharpe ratio (zero risk-free rate)",
        "Sentiment tilted": summary["strategy_sharpe_zero_rf"],
        "Equal weight": summary["equal_weight_sharpe_zero_rf"],
    },
    {
        "Metric": "Maximum drawdown",
        "Sentiment tilted": summary["strategy_max_drawdown"],
        "Equal weight": summary["equal_weight_max_drawdown"],
    },
]

if "spy_cumulative_return" in summary:
    for label, key in [
        ("Cumulative return", "cumulative_return"),
        ("Annualized volatility", "annualized_volatility"),
        ("Sharpe ratio (zero risk-free rate)", "sharpe_zero_rf"),
        ("Maximum drawdown", "max_drawdown"),
    ]:
        summary_key = f"spy_{key}"
        if summary_key in summary:
            stats_rows.append(
                {
                    "Metric": f"SPY — {label}",
                    "Sentiment tilted": None,
                    "Equal weight": None,
                    "SPY": summary[summary_key],
                }
            )

st.dataframe(
    pd.DataFrame(stats_rows), use_container_width=True, hide_index=True
)

st.divider()
st.subheader("Allocation over time")
st.caption(
    "Use the date slider below to inspect a specific allocation. The heatmap is "
    "sampled every fifth trading date for readability; downloaded data remains daily."
)

heatmap_weights = chart_weights.pivot(
    index="ticker", columns="date", values="weight"
).sort_index()
if heatmap_weights.empty:
    st.warning("No allocations are available for the selected chart range.")
    st.stop()

heatmap_sample = heatmap_weights.iloc[:, ::5]
if heatmap_sample.shape[1] == 0:
    heatmap_sample = heatmap_weights

weight_min = float(weights["weight"].quantile(0.02))
weight_max = float(weights["weight"].quantile(0.98))
if weight_min == weight_max:
    weight_max = weight_min + 1e-6

fig_heat = go.Figure(
    data=go.Heatmap(
        z=heatmap_sample.to_numpy(),
        x=heatmap_sample.columns,
        y=heatmap_sample.index,
        colorscale="Blues",
        colorbar=dict(title="Weight", tickformat=".1%"),
        zmin=max(0.0, weight_min),
        zmax=weight_max,
        hovertemplate=(
            "Date: %{x|%Y-%m-%d}<br>"
            "Ticker: %{y}<br>"
            "Weight: %{z:.2%}<extra></extra>"
        ),
    )
)
fig_heat.update_layout(
    template="plotly_dark",
    height=520,
    margin=dict(l=10, r=10, t=20, b=10),
    xaxis_title="Date",
    yaxis_title="Ticker",
)
st.plotly_chart(fig_heat, use_container_width=True)

all_dates = sorted(chart_weights["date"].dropna().unique())
if not all_dates:
    st.warning("No dates are available for allocation inspection.")
    st.stop()

selected_date = st.select_slider(
    "Inspect allocation date",
    options=all_dates,
    value=all_dates[-1],
    format_func=lambda value: pd.Timestamp(value).strftime("%Y-%m-%d"),
)

selected = (
    chart_weights[chart_weights["date"] == selected_date]
    .copy()
    .sort_values("weight", ascending=False)
)

available_tickers = sorted(selected["ticker"].dropna().unique().tolist())
if not available_tickers:
    st.warning("No stock allocations are available on this date.")
    st.stop()

default_ticker = (
    MOCK_INDEX_TICKERS[0]
    if MOCK_INDEX_TICKERS[0] in available_tickers
    else available_tickers[0]
)
selected_ticker = st.selectbox(
    "Inspect stock",
    available_tickers,
    index=available_tickers.index(default_ticker),
)

ticker_rows = selected[selected["ticker"] == selected_ticker]
if ticker_rows.empty:
    st.warning(f"No allocation data available for {selected_ticker} on {selected_date}.")
    st.stop()

row = ticker_rows.iloc[0]
base_value = row.get("equal_weight_baseline", 1.0 / max(1, universe_count))
base = float(base_value) if pd.notna(base_value) else 1.0 / max(1, universe_count)
actual_value = row.get("weight", 0.0)
actual = float(actual_value) if pd.notna(actual_value) else 0.0
sentiment_value = row.get("signal_sentiment", 0.0)
sentiment = (
    float(sentiment_value)
    if pd.notna(sentiment_value)
    else 0.0
)
active = actual - base

st.markdown("#### Allocation audit")
a1, a2, a3, a4 = st.columns(4)
a1.metric(
    f"{selected_ticker} weight",
    f"{actual:.2%}",
    f"{active:+.2%} vs equal weight",
)
a2.metric("Equal-weight baseline", f"{base:.2%}")
a3.metric(
    "Aggregated sentiment",
    f"{sentiment:+.3f}",
    help="Confidence-weighted, time-decayed sentiment in the configured lookback window.",
)

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
    st.warning(
        "Positive sentiment is not above the equal-weight baseline on this date. "
        "Other stocks' signals, the weight cap, and turnover constraints can affect "
        "the final allocation. Inspect the time series before treating this as a "
        "directional failure."
    )
elif sentiment < 0 and active >= -1e-6:
    st.warning(
        "Negative sentiment is not below the equal-weight baseline on this date. "
        "Other stocks' signals, the weight cap, and turnover constraints can affect "
        "the final allocation. Inspect the time series before treating this as a "
        "directional failure."
    )

fig_bar = px.bar(
    selected.sort_values("weight"),
    x="weight",
    y="ticker",
    orientation="h",
    title=f"Portfolio weights on {pd.Timestamp(selected_date).strftime('%Y-%m-%d')}",
    labels={"weight": "Portfolio weight", "ticker": "Stock"},
)
fig_bar.add_vline(
    x=base,
    line_dash="dash",
    line_color="#F59E0B",
    annotation_text=f"Equal weight {base:.2%}",
)
fig_bar.update_layout(
    template="plotly_dark",
    height=520,
    margin=dict(l=10, r=10, t=45, b=10),
    xaxis_tickformat=".1%",
)
st.plotly_chart(fig_bar, use_container_width=True)

selected_ticker_history = (
    chart_weights[chart_weights["ticker"] == selected_ticker].sort_values("date")
)
fig_ticker = go.Figure()
fig_ticker.add_trace(
    go.Scatter(
        x=selected_ticker_history["date"],
        y=selected_ticker_history["weight"],
        mode="lines",
        name=f"{selected_ticker} weight",
    )
)
fig_ticker.add_hline(
    y=base,
    line_dash="dash",
    line_color="#F59E0B",
    annotation_text=f"Equal weight {base:.2%}",
)
fig_ticker.update_layout(
    template="plotly_dark",
    height=320,
    margin=dict(l=10, r=10, t=20, b=10),
    xaxis_title="Date",
    yaxis_title="Weight",
    yaxis_tickformat=".1%",
)
st.plotly_chart(fig_ticker, use_container_width=True)

st.subheader("Daily allocation table")
table_columns = [
    "ticker",
    "weight",
    "equal_weight_baseline",
    "active_weight",
    "signal_sentiment",
]
for column in table_columns:
    if column not in selected.columns:
        if column == "equal_weight_baseline":
            selected[column] = 1.0 / max(1, universe_count)
        elif column == "active_weight":
            selected[column] = (
                selected.get("weight", 0.0) - selected["equal_weight_baseline"]
            )
        else:
            selected[column] = 0.0

show = selected[table_columns].copy().rename(
    columns={
        "ticker": "Ticker",
        "weight": "Weight",
        "equal_weight_baseline": "Equal weight",
        "active_weight": "Difference",
        "signal_sentiment": "Sentiment",
    }
)
st.dataframe(
    show.style.format(
        {
            "Weight": "{:.2%}",
            "Equal weight": "{:.2%}",
            "Difference": "{:+.2%}",
            "Sentiment": "{:+.3f}",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "⬇ Download daily weights",
    weights.to_csv(index=False).encode("utf-8"),
    "weights_over_time.csv",
    "text/csv",
)
st.download_button(
    "⬇ Download performance series",
    daily.to_csv(index=False).encode("utf-8"),
    "performance_comparison.csv",
    "text/csv",
)
st.caption(
    f"Charts show: {'full history' if chart_window == 0 else f'last {chart_window} months'}. "
    f"CSV downloads retain the full backtest. Eligible signal rows: {len(eligible_signals):,} · "
    f"Signal-bearing tickers: {active_tickers}/{universe_count} · "
    f"Turnover cap: {turnover:.0%} per rebalance · Transaction costs excluded."
)
