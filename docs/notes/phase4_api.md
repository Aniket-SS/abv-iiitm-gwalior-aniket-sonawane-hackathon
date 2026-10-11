# Phase 4: SQLite signal store and FastAPI

## Components

- `src/signals/store.py`: SQLite schema, indexes, idempotent upsert, filtered queries, and confidence-filtered exponentially decayed aggregation.
- `scripts/import_signals.py`: validates JSONL records against `Signal` and imports them in batches.
- `src/api/app.py`: read-only API for health, signal queries, single-signal lookup, and aggregate signals.

## Default configuration

The database path comes from `config/settings.yaml` (`paths.signals_db`, default `data/processed/signals.db`). Override it with `SIGNALS_DB_PATH` for the API or `--db` for the importer.

Aggregation defaults to the configured 7-day window, 48-hour half-life, and minimum confidence 0.5. The weight is `confidence * 0.5 ** (age_hours / half_life_hours)`. Company and market scopes remain separate aggregation groups.

## Local usage (PowerShell)

```powershell
python -m pip install "fastapi>=0.110,<1" "uvicorn[standard]>=0.27,<1" "httpx>=0.27,<1"
python -m scripts.import_signals data/processed/phase3_all_signals.jsonl
python -m uvicorn src.api.app:app --reload
```

Open `http://127.0.0.1:8000/docs`. Useful endpoints: `/health`, `/signals`, `/signals/{signal_id}`, and `/signals/aggregate`. The aggregate endpoint accepts an optional `as_of` ISO datetime so historical datasets can be queried relative to their own dates.

Do not commit generated signal JSONL, raw source datasets, `.env`, or the SQLite database. The current imported signals are from the Phase 3 rules/lexicon baseline, not pretrained model inference.
