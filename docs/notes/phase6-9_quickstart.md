# Phase 6–9 Quickstart and acceptance checklist

From the repository root, with the project's virtual environment activated:

```powershell
python -m pip install "streamlit>=1.38,<2" "plotly>=5.20"
python -m pytest -q
```

The full dashboard is launched with one command:

```powershell
python -m streamlit run src/dashboard/app.py
```

It expects `data/processed/signals.db` and `data/raw/prices/prices_daily.csv` to exist. Populate those using the existing ingestion, engine, import, and price-fetch steps before the demo.

## Module A: index rebalancer

```powershell
python -m scripts.run_rebalancer
```

Outputs are generated locally in `data/processed/phase6/`:

- `weights_over_time.csv`
- `performance_comparison.csv`
- `performance_summary.json`

The equal-weight portfolio is static. The sentiment strategy uses a 7-calendar-day lookback, 48-hour half-life, 0.5 minimum confidence, 15% single-name cap, and 10% maximum one-way turnover per rebalance by default. These are tunable demo assumptions; transaction costs are not included.

## Module B: stress tester

```powershell
python -m scripts.run_stress_test --threshold 7
```

It selects the most recent signal at or above the threshold and writes `data/processed/phase7/latest_stress_test.json`. To choose a particular signal:

```powershell
python -m scripts.run_stress_test --signal-id YOUR_SIGNAL_ID --threshold 7
```

The synthetic portfolio is `data/synthetic/wholesale_portfolio.csv`; shocks are configured in `config/stress_scenarios.yaml`.

## Deliverables checklist

- [ ] `docs/architecture.md` architecture flow reviewed and exported to a screenshot/PDF if needed.
- [ ] 5–7 slide deck saved to `docs/presentation.pptx` or `docs/presentation.pdf`.
- [ ] Demo video recorded and uploaded; add a publicly accessible link to README.
- [ ] README contains actual repository URL, setup steps, data sources, assumptions, and demo/deck links.
- [ ] Run `python -m pytest -q` in a fresh environment.
- [ ] Verify public repository, slide link, and video link in a signed-out/incognito browser.
- [ ] Keep `.env` and API keys out of Git. Commit small synthetic/demo data; do not commit credentials or large raw datasets.
