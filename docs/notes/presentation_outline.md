# Seven-slide presentation outline

Use this outline to create `docs/presentation.pptx` or `docs/presentation.pdf`. Keep the deck to 5–7 slides as required by the submission brief.

1. **Title and objective** — Code to Connect; real-time unstructured news/social data converted into actionable financial risk signals; candidate, campus, repository and demo links.
2. **Problem and approach** — fragmented unstructured feeds; normalize documents, identify ticker/scope, score sentiment/event/impact, persist structured signals.
3. **Architecture** — use `docs/architecture.md`; ingestion → NLP engine → SQLite/API → live feed, index rebalancer and stress tester.
4. **Risk Engine implementation** — sources used, schema (`ticker`, `sentiment`, `event_type`, `impact`, `confidence`, `scope`), current rule/model approach, explainable rationale and data-quality limitations.
5. **Module A: index rebalancer** — show `weights_over_time.csv`, strategy versus static equal-weight growth chart, turnover and max-weight settings. Insert actual values from `performance_summary.json` after running the backtest; do not invent results.
6. **Module B: stress tester** — show the synthetic portfolio mix, chosen high-impact signal, configured event shock, before/after valuation and asset-level P&L. Insert a screenshot from a real run.
7. **Results, impact and limitations** — report current test count from the final clean run, observed backtest/stress outputs, data coverage, simplified sensitivities, transaction-cost omission, experimental learned score, and next steps.

The model-calibration holdout correlation previously observed was about 0.428 after a 7-day purge, against a baseline of about -0.302. Label this exploratory, time-split association—not validated live predictive performance—and refresh the numbers after any retraining.
