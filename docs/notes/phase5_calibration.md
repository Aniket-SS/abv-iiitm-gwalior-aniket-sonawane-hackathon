# Phase 5 — Impact calibration

## Corrected event timing

The event study now starts from the first available trading date strictly after the signal's calendar date. With daily prices, intraday publication time cannot be resolved, so this conservative policy avoids using the same-day close as if it were known after every event. The return horizon is measured from that matched close to the close `horizon` trading sessions later.

## Learned impact calibration

After regenerating the event study, run:

```powershell
python -m scripts.calibrate_impact --prices data/raw/prices/prices_daily.csv --db data/processed/signals.db
python -m scripts.train_impact_calibrator --events data/processed/phase5/impact_event_study.csv --horizon 3
```

The learned layer uses a Random Forest regressor to estimate the absolute magnitude of subsequent abnormal return from existing impact, confidence, absolute sentiment, event type, channel, scope, and ticker. The target is log-transformed during training. Same-ticker/same-date observations are aggregated before the chronological split to reduce duplicate-event dependence. The latest 20% of unique ticker/date observations form the holdout; only earlier observations are used for the holdout model. A deployable model is then fitted on all observations for future experimentation.

Outputs are written under `data/processed/phase5/`: `learned_impact_model.joblib`, `learned_impact_metrics.json`, and `learned_impact_holdout.csv`. These are generated local artifacts and should not be committed.

## Acceptance criteria

Compare the holdout Spearman correlation of the original impact score against the correlation of predicted absolute abnormal return with the observed absolute abnormal return. Inspect errors and score bands. If the learned model does not outperform the original score on held-out dates, do not claim improvement. The learned model estimates movement magnitude, not direction, and is exploratory rather than a trading guarantee.
