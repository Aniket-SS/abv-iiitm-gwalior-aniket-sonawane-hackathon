# Phase 5 — Impact calibration report

## Run metadata

- Generated: 2026-10-11
- Signals in SQLite: 109,262
- Signals with a matched starting price date: 108,579
- Signals with a complete 3-day outcome: 108,360
- Price date range: 2021-09-30 to 2026-10-09
- Price tickers: AAPL, AMD, AMZN, BA, COST, CRM, DIS, GOOG, INTC, KO, META, MSFT, NFLX, PG, SPY, TSLA, VZ
- Benchmark: SPY
- Evaluation horizon: 3 trading days

## Results

- Spearman correlation between existing impact score and absolute abnormal return: -0.093702
- Mean absolute abnormal return: 3.124836

| Impact band | Signals | Mean absolute abnormal return (%) | Median absolute abnormal return (%) |
|---|---:|---:|---:|
| 1-3 | 88404 | 3.1976 | 2.1642 |
| 4-6 | 11420 | 3.2272 | 2.2158 |
| 7-8 | 6348 | 2.1387 | 1.2004 |
| 9-10 | 920 | 2.3941 | 1.4004 |

## Interpretation and limitations

This is an exploratory event-study diagnostic, not proof of causality or predictive performance. A positive correlation means higher existing impact scores tended to coincide with larger absolute abnormal returns in this matched sample; it does not establish that the signal predicted those returns. Daily prices cannot resolve the intraday publication time, event observations can overlap, signals can be duplicated across sources, and historical price coverage may exclude tickers or dates. Market-scope signals use the benchmark's own return as the outcome. Company-scope abnormal return is ticker return minus benchmark return. Impact scores are not modified by this script.

## Files

- Event-level observations: `data/processed/phase5/impact_event_study.csv`
- Machine-readable summary: `data/processed/phase5/impact_calibration_summary.json`
