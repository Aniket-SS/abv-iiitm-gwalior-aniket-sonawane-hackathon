# Phase 2 — Ingestion adapters

## Scope

Normalize four text-source families into the existing `src.common.schemas.Document` contract:

1. Historical `stock_tweets.csv` — local replay data, filtered to configured tickers.
2. GDELT bulk GKG files — headline/metadata records, processed locally (`scripts/process_gdelt.py`, then `scripts/ingest_gdelt_processed.py`). The live GDELT DOC API adapter was removed: it is rate-limited and not useful for this project.
3. NewsAPI — recent headlines and descriptions only, with `NEWSAPI_API_KEY` read from `.env`.
4. `news_vs_market_2020/news_sentiment_raw.csv` — existing dated article records; source-provided VADER scores are preserved as metadata, not treated as engine output.

Every document uses UTC timestamps, a deterministic ID, source/channel metadata, and `raw_meta.entity_scope`, `raw_meta.entities`, and `raw_meta.tickers`. Market-wide stories are retained with an empty ticker list; the adapter does not invent a company link. Article bodies are not scraped or stored; NewsAPI's title and description are used.

## Files

- `src/ingestion/normalization.py`: timestamp parsing, deterministic IDs, conservative ticker linking, deduplication helpers.
- `src/ingestion/historical_tweets.py`: historical social dataset adapter.
- `src/ingestion/gdelt.py` and `src/ingestion/gdelt_processed.py`: parse the bulk GDELT GKG/export/mentions files and normalize GKG headline records.
- `src/ingestion/newsapi.py`: NewsAPI adapter using environment credentials.
- `src/ingestion/news_vs_market.py`: normalizes the existing article CSV and preserves source sentiment metadata.
- `scripts/ingest_news_vs_market.py`: local CSV adapter CLI.
- `src/ingestion/storage.py`: validated JSONL read/write and merge.
- `scripts/ingest_tweets.py`, `scripts/ingest_gdelt_processed.py`, `scripts/ingest_newsapi.py`, `scripts/merge_ingestion.py`: CLI entry points.
- `tests/test_ingestion_phase2.py`: offline tests; live API calls are not part of unit tests.

## Install / setup (PowerShell)

```powershell
pip install -r requirements.txt
```

Add this line to `.env` only if you have a NewsAPI key:

```dotenv
NEWSAPI_API_KEY=your_key_here
```

Do not commit `.env`. If `.env.example` is used, it should contain only a blank placeholder.

## Run in order

```powershell
python -m scripts.ingest_tweets --limit 100
python -m scripts.ingest_tweets
python -m scripts.process_gdelt
python -m scripts.ingest_gdelt_processed
python -m scripts.ingest_news_vs_market --limit 100
python -m scripts.ingest_news_vs_market
python -m scripts.ingest_newsapi --days-back 7 --page-size 100
python -m scripts.merge_ingestion data/processed/ingestion/stock_tweets.jsonl data/processed/ingestion/news_vs_market.jsonl data/processed/ingestion/gdelt_documents.jsonl data/processed/ingestion/newsapi_recent.jsonl
pytest -q
```

The first tweet command is a smoke test; the second replaces the output with the full configured-universe historical tweet set. GDELT processing reads files already downloaded under `data/raw/gdelt/extracted`. Only NewsAPI needs internet access, a valid key and a plan that permits the request. To merge only sources that have successfully run, pass only those JSONL paths to `merge_ingestion`.

## Important behavior and limits

- Historical replay stays on `2021-09-30` to `2022-09-29`; live feeds are separate recent coverage and must not be backfilled into that historical window.
- GDELT comes only from the downloaded bulk GKG files (recent window, headline/metadata only). Its records are not linked to a ticker at ingestion (`entity_scope=unlinked`); linking happens in the Phase 3 engine.
- NewsAPI is not called by the tweet adapter and no API key is required for local tweet ingestion.
- Entity linking is deliberately conservative and uses `config/tickers.yaml`. Matching is case-aware: `$CASHTAGS`, UPPER-case symbols, and company names; ambiguous symbols/names (COST, BA, KO, PG, DIS, META, CRM; Apple, Meta, Intel, Amazon, Coke, AWS) need stricter evidence (see `AMBIGUOUS_SYMBOLS` / `AMBIGUOUS_NAMES` in `src/ingestion/normalization.py`). If there is no reliable match, the record is kept as `entity_scope=market` with `tickers=[]`. The `tickers` field written at ingestion is only a hint; the Phase 3 engine re-links from the text.
- A tweet tagged with several tickers in the source CSV becomes one `Document` per ticker (the ticker is part of the document id). Identical rows (same text, ticker and timestamp) still collapse into one.
- `Document` is an ingestion contract, not a risk `Signal`. Sentiment, event type, impact and confidence are produced in Phase 3.
- Deduplication uses normalized URL when available; without a URL it uses the deterministic document ID.
- The historical tweets adapter expects columns `Date`, `Tweet`, `Stock Name`, and `Company Name`. It drops rows with invalid timestamps, blank text, or no configured ticker match.
- The current adapter retains title/description rather than publisher article bodies. Follow source terms and preserve original URLs/attribution.

## Phase 2 completion checks

- [ ] Tweet adapter creates valid `Document` JSONL and preserves source timestamp/ticker.
- [ ] GDELT GKG adapter creates valid `Document` JSONL; stories remain unlinked until Phase 3.
- [ ] NewsAPI adapter creates valid recent `Document` JSONL with key kept outside source control.
- [ ] Merged output has no duplicate URLs and every line validates as `Document`.
- [ ] Unit tests pass without network access.
- [ ] Record API query, retrieval time, count, source URL and known coverage limits in project docs.


## Dataset roles outside text ingestion

`market_prices.csv` and project price files remain tabular market inputs. `news_sentiment_daily.csv`, `sentiment_market_panel.csv`, and `ml_features.csv` are derived analytical files and are not independent article streams. SEntFiN and Financial PhraseBank-style data remain evaluation candidates because they lack publication timestamps. `market_events_2025` remains a taxonomy/rule-testing reference; `tweets_returns` remains excluded due to malformed field/date alignment. See `docs/notes/data_decisions.md` and `docs/notes/data_licensing_phase1.md`.
