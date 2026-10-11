# Phase 2 — Ingestion adapters

## Scope

Normalize four text-source families into the existing `src.common.schemas.Document` contract:

1. Historical `stock_tweets.csv` — local replay data, filtered to configured tickers.
2. GDELT DOC API — recent news/event headlines only.
3. NewsAPI — recent headlines and descriptions only, with `NEWSAPI_API_KEY` read from `.env`.
4. `news_vs_market_2020/news_sentiment_raw.csv` — existing dated article records; source-provided VADER scores are preserved as metadata, not treated as engine output.

Every document uses UTC timestamps, a deterministic ID, source/channel metadata, and `raw_meta.entity_scope`, `raw_meta.entities`, and `raw_meta.tickers`. Market-wide stories are retained with an empty ticker list; the adapter does not invent a company link. Article bodies are not scraped or stored; NewsAPI's title and description are used.

## Files

- `src/ingestion/normalization.py`: timestamp parsing, deterministic IDs, conservative ticker linking, deduplication helpers.
- `src/ingestion/historical_tweets.py`: historical social dataset adapter.
- `src/ingestion/gdelt_api.py`: GDELT DOC API adapter with a 250-record maximum and five-second spacing helper for multi-query calls.
- `src/ingestion/newsapi.py`: NewsAPI adapter using environment credentials.
- `src/ingestion/news_vs_market.py`: normalizes the existing article CSV and preserves source sentiment metadata.
- `scripts/ingest_news_vs_market.py`: local CSV adapter CLI.
- `src/ingestion/storage.py`: validated JSONL read/write and merge.
- `scripts/ingest_tweets.py`, `scripts/ingest_gdelt.py`, `scripts/ingest_newsapi.py`, `scripts/merge_ingestion.py`: CLI entry points.
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
python -m scripts.ingest_gdelt --timespan 1week --max-records 100
python -m scripts.ingest_news_vs_market --limit 100
python -m scripts.ingest_news_vs_market
python -m scripts.ingest_newsapi --days-back 7 --page-size 100
python -m scripts.merge_ingestion data/processed/ingestion/stock_tweets.jsonl data/processed/ingestion/news_vs_market.jsonl data/processed/ingestion/gdelt_recent.jsonl data/processed/ingestion/newsapi_recent.jsonl
pytest -q
```

The first command is a smoke test; the second replaces the output with the full configured-universe historical tweet set. GDELT and NewsAPI require internet access. NewsAPI also requires a valid key and a plan that permits the request. To merge only sources that have successfully run, pass only those JSONL paths to `merge_ingestion`.

## Important behavior and limits

- Historical replay stays on `2021-09-30` to `2022-09-29`; live feeds are separate recent coverage and must not be backfilled into that historical window.
- GDELT's article search is a recent index; the downloaded bulk GDELT files are a separate experimental dataset and are not automatically mixed into this output.
- NewsAPI is not called by the tweet adapter and no API key is required for local tweet ingestion.
- Entity linking is deliberately conservative and uses `config/tickers.yaml`. If there is no reliable match, the record is kept as `entity_scope=market` with `tickers=[]`.
- `Document` is an ingestion contract, not a risk `Signal`. Sentiment, event type, impact and confidence are produced in Phase 3.
- Deduplication uses normalized URL when available; without a URL it uses the deterministic document ID.
- The historical tweets adapter expects columns `Date`, `Tweet`, `Stock Name`, and `Company Name`. It drops rows with invalid timestamps, blank text, or no configured ticker match.
- The current adapter retains title/description rather than publisher article bodies. Follow source terms and preserve original URLs/attribution.

## Phase 2 completion checks

- [ ] Tweet adapter creates valid `Document` JSONL and preserves source timestamp/ticker.
- [ ] GDELT adapter creates valid recent `Document` JSONL; market-level stories remain unlinked.
- [ ] NewsAPI adapter creates valid recent `Document` JSONL with key kept outside source control.
- [ ] Merged output has no duplicate URLs and every line validates as `Document`.
- [ ] Unit tests pass without network access.
- [ ] Record API query, retrieval time, count, source URL and known coverage limits in project docs.


## Dataset roles outside text ingestion

`market_prices.csv` and project price files remain tabular market inputs. `news_sentiment_daily.csv`, `sentiment_market_panel.csv`, and `ml_features.csv` are derived analytical files and are not independent article streams. SEntFiN and Financial PhraseBank-style data remain evaluation candidates because they lack publication timestamps. `market_events_2025` remains a taxonomy/rule-testing reference; `tweets_returns` remains excluded due to malformed field/date alignment. See `docs/notes/data_decisions.md` and `docs/notes/data_licensing_phase1.md`.
