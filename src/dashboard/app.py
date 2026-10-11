from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.data_access import all_signals, database_path, event_type_counts, signal_count

st.set_page_config(page_title="Code to Connect | Risk Intelligence", page_icon="🔎", layout="wide")
st.markdown("""<style>
.eyebrow{color:#7dd3fc;font-size:.78rem;font-weight:700;letter-spacing:.14em;margin-bottom:-.5rem}
[data-testid="stMetric"]{background:rgba(125,211,252,.06);border:1px solid rgba(148,163,184,.18);padding:14px 16px;border-radius:12px}
[data-testid="stSidebarNav"]{padding-top:1rem}
</style>""", unsafe_allow_html=True)
st.markdown("<div class='eyebrow'>CODE TO CONNECT · HACKATHON DEMO</div>", unsafe_allow_html=True)
st.title("Financial Risk Intelligence")
st.caption("A shared NLP risk-signal database powering sentiment-based index rebalancing and event-driven portfolio stress testing.")

if st.button("↻ Refresh database analytics"):
    st.cache_data.clear()
    st.rerun()

@st.cache_data(ttl=120, show_spinner="Reading the complete signal database…")
def load_full_database():
    return all_signals(), event_type_counts(), signal_count()

try:
    db_file = database_path()
    signals, event_counts, total_count = load_full_database()
except Exception as exc:
    st.error("The stored NLP risk-signal database could not be read. Check the database setup.")
    st.exception(exc)
    st.stop()

if not db_file.exists() or signals.empty:
    st.warning("No stored signals were found. Run the ingestion and NLP pipeline first.")
    st.stop()

signals = signals.copy()
signals["timestamp"] = pd.to_datetime(signals["timestamp"], errors="coerce", utc=True)
for column in ["sentiment", "impact", "confidence"]:
    signals[column] = pd.to_numeric(signals[column], errors="coerce")
valid_sentiment = signals.dropna(subset=["sentiment"]).copy()
valid_sentiment = valid_sentiment[valid_sentiment["sentiment"].between(-1, 1)]
latest_time = signals["timestamp"].max()

negative = int((valid_sentiment["sentiment"] < -0.05).sum())
neutral = int(valid_sentiment["sentiment"].between(-0.05, 0.05, inclusive="both").sum())
positive = int((valid_sentiment["sentiment"] > 0.05).sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total stored signals", f"{total_count:,}")
m2.metric("Event categories", f"{len(event_counts):,}")
m3.metric("Numeric sentiment scores", f"{len(valid_sentiment):,}")
m4.metric("Latest signal (UTC)", latest_time.strftime("%d %b %Y, %H:%M") if pd.notna(latest_time) else "Unavailable")

st.info("**How to explore:** Module A uses historical company-specific sentiment signals with price history. Module B uses stored event classifications and impact scores to select a stress scenario for a synthetic portfolio.")
st.subheader("Event classification across the full database")
st.caption("Counts below are grouped across all stored signals, not just the latest feed rows. ‘Other’ means the NLP classifier or upstream data did not assign a more specific category.")
if not event_counts.empty:
    event_counts["event_type"] = event_counts["event_type"].fillna("other").astype(str)
    event_counts["Event type"] = event_counts["event_type"].str.replace("_", " ").str.title()
    fig_events = px.bar(event_counts.sort_values("signals"), x="signals", y="Event type", orientation="h", text="signals", labels={"signals": "Stored signals"}, title="All stored signals by event type")
    fig_events.update_layout(template="plotly_dark", height=max(380, 34 * len(event_counts)), margin=dict(l=10, r=20, t=50, b=10), yaxis_title=None)
    st.plotly_chart(fig_events, use_container_width=True)

left, right = st.columns([0.9, 1.1])
with left:
    st.subheader("Sentiment balance")
    st.caption("Full database; neutral is defined as a score between −0.05 and +0.05.")
    sentiment_balance = pd.DataFrame({"Sentiment": ["Negative", "Neutral", "Positive"], "Signals": [negative, neutral, positive]})
    sentiment_balance["Share"] = sentiment_balance["Signals"] / max(1, sentiment_balance["Signals"].sum())
    fig_balance = px.bar(sentiment_balance, x="Sentiment", y="Signals", text=sentiment_balance.apply(lambda r: f"{int(r['Signals']):,} · {r['Share']:.1%}", axis=1), color="Sentiment", category_orders={"Sentiment": ["Negative", "Neutral", "Positive"]}, title="Negative, neutral and positive signals")
    fig_balance.update_layout(template="plotly_dark", height=350, showlegend=False, margin=dict(l=10, r=10, t=50, b=10), xaxis_title=None)
    st.plotly_chart(fig_balance, use_container_width=True)
with right:
    st.subheader("Non-neutral sentiment distribution")
    non_neutral = valid_sentiment[valid_sentiment["sentiment"].abs() > 0.05]
    if non_neutral.empty:
        st.info("No non-neutral scores are present in the stored database.")
    else:
        fig_hist = px.histogram(non_neutral, x="sentiment", nbins=30, labels={"sentiment": "Sentiment score"}, title="Score frequency, excluding neutral scores")
        fig_hist.update_layout(template="plotly_dark", height=350, margin=dict(l=10, r=10, t=50, b=10), xaxis_title="Sentiment (−1 negative to +1 positive)", yaxis_title="Signals")
        st.plotly_chart(fig_hist, use_container_width=True)

st.subheader("Latest risk signals")
st.caption("This table shows the 15 newest records for quick inspection. The charts above use the full database.")
cols = [c for c in ["timestamp", "ticker", "scope", "event_type", "sentiment", "impact", "confidence", "source"] if c in signals.columns]
latest = signals.sort_values("timestamp", ascending=False).head(15).copy()
if "timestamp" in latest:
    latest["timestamp"] = latest["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")
st.dataframe(latest[cols], use_container_width=True, hide_index=True)

with st.expander("About the demonstration and data"):
    st.markdown("""
- **Full-database analytics:** Event counts and sentiment summaries use all stored signal records.
- **Module A:** Historical backtesting with stored company-specific sentiment signals and daily price history. This is not an order-execution system.
- **Module B:** Stored risk signals choose a configured shock scenario, which is applied to a synthetic wholesale portfolio.
- Portfolio shocks, sensitivities and valuations are illustrative assumptions, not forecasts or actual bank risk estimates.
""")
