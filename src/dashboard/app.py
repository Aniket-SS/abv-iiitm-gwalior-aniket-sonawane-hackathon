from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plotly.express as px
import streamlit as st

from src.dashboard.data_access import database_path, recent_signals, signal_count

st.set_page_config(page_title="Code to Connect | Risk Engine", page_icon="📊", layout="wide")
st.title("Code to Connect — Financial Risk Intelligence")
st.caption("NLP risk signals, sentiment-tilted index rebalancing, and event-driven portfolio stress testing.")

left, middle, right = st.columns(3)
left.metric("Stored risk signals", f"{signal_count():,}")
middle.metric("Signal database", "Available" if database_path().exists() else "Not found")
right.metric("Downstream modules", "2")

if not database_path().exists():
    st.error(f"Signal database not found: {database_path()}")
    st.info("Run the ingestion, NLP engine, and signal-import steps first. See the README Quickstart.")
    st.stop()

st.subheader("Risk Engine live feed")
refresh_col, limit_col = st.columns([1, 2])
with refresh_col:
    st.button("Refresh feed", use_container_width=True)
with limit_col:
    limit = st.selectbox("Rows to display", [25, 50, 100, 250], index=1)
feed = recent_signals(limit=limit)
if feed.empty:
    st.info("No signals are available in the database yet.")
else:
    event_counts = feed.groupby("event_type", dropna=False).size().reset_index(name="signals")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.plotly_chart(px.bar(event_counts, x="event_type", y="signals", title="Event types in current feed"), use_container_width=True)
    with c2:
        sentiment = feed.groupby("channel", dropna=False)["sentiment"].mean().reset_index()
        st.plotly_chart(px.bar(sentiment, x="channel", y="sentiment", title="Mean sentiment by channel", range_y=[-1, 1]), use_container_width=True)
    display_cols = [c for c in ["timestamp", "ticker", "scope", "event_type", "sentiment", "impact", "confidence", "source", "text_snippet"] if c in feed]
    st.dataframe(feed[display_cols], use_container_width=True, hide_index=True)

st.subheader("How to use the dashboard")
st.markdown("""
- **Index Rebalancer:** compare a sentiment-tilted index with a static equal-weight index and download the weights-over-time table.
- **Stress Tester:** select a high-impact signal and apply the corresponding configured shock to a synthetic wholesale portfolio.
- **Interpretation:** all backtests and portfolio shocks are prototypes. Historical association and simplified scenario P&L are not investment advice or a production bank risk model.
""")
