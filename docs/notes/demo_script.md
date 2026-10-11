# Demo walkthrough checklist (recording target: 5–8 minutes)

1. **Intro (30–45 sec):** state the risk-intelligence problem and the two downstream uses.
2. **Launch (30 sec):** from a clean terminal, show the README Quickstart and run `python -m streamlit run src/dashboard/app.py`.
3. **Risk Engine feed (60 sec):** show recent stored signals, ticker, scope, sentiment, event type, impact, confidence, and source.
4. **Index Rebalancer (90 sec):** show universe/date coverage, compare the sentiment-tilted portfolio to static equal weight, change the turnover cap, inspect the latest weights, download the CSV.
5. **Stress Tester (90 sec):** choose a stored high-impact signal; show the selected scenario shocks, portfolio before/after, total P&L and asset-level contributions. If no signal meets the threshold, explicitly label a synthetic demo event rather than presenting it as real.
6. **Wrap-up (30 sec):** explain data assumptions, the synthetic portfolio, transaction-cost omission, and that learned impact calibration remains experimental.

Before upload, ensure the recording is viewable by reviewers (unlisted/public link with access tested in an incognito browser). Add the actual video URL to README only after testing it.
