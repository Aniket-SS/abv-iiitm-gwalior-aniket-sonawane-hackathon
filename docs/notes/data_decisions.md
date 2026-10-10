# Data Decisions — Code to Connect

**Status:** Implementation decisions for Phase 1. Update this file when source roles, measured coverage, or terms change. This file is the source of truth for the README's data and licensing sections.

## 1. Objective and canonical signal

Build one risk-signal pipeline that ingests company-specific news and broader event/market text. The coverage target is 2021–present, but do not claim continuous coverage until local profiling demonstrates it.

Every record must have a scope:
- `company`: a company/ticker is linked with evidence;
- `event`: a broader event is identified but no company can be reliably linked;
- `market`: broad market conditions or sentiment are discussed.

Never invent a ticker to fill a missing field. Company-level signals can drive Module A. Event- and market-level signals can drive Module B when they match documented shock rules.

The normalized record should preserve, when available: publication time, retrieval time, headline/text, URL, publisher/source, source type, original ticker/entity, normalized ticker/company, source record ID, and provenance/terms notes.

The risk engine should output:
- sentiment in `[-1, 1]`;
- event category;
- impact in `[1, 10]`;
- model confidence, separate from impact;
- scope (`company`, `event`, or `market`);
- short rationale/evidence and source URL.

## 2. Selected data sources

| Source | Role | Coverage/limits | Implementation decision |
|---|---|---|---|
| Existing `stock_tweets/stock_tweets.csv` + `stock_yfinance_data.csv` | Historical social-sentiment replay and Module A backtest | Tweets and prices span 2021-09-30 to 2022-09-29; 25 tickers, 80,793 tweets, 6,300 price rows | Keep as the reproducible baseline. Deduplicate carefully; TSLA is about 46% of tweets. Do not assume `GOOG` and `GOOGL` are interchangeable. |
| **FNSPID (partial mirror subset)** | Optional supplementary historical company-news sample only | The tested JSONL mirror yielded 18,483 records for AAPL (8,865), AMD (4,836), and AMZN (4,782), with zero records for the other 13 selected tickers; dates span 2021-01-04 to 2023-12-31. | **Do not rely on it for the 16-stock universe.** Keep the extracted subset locally for optional experiments, but do not spend more time scanning the 23.2 GB CSV or treating this mirror as complete. The mirror may be incomplete or uneven; represent its coverage exactly as measured. |
| **GDELT DOC API** | Primary recent/global news adapter; useful for company, event and market signals | DOC API is a rolling recent-news search service (roughly the last three months), not a complete historical archive | Implement as a small, rate-conscious adapter. Keep URL, title, publisher/domain, seen/publication time, retrieval time, and query. Expect incomplete results and deduplicate by URL/title. |
| **NewsAPI.org** | Optional secondary recent-news adapter and development/testing source | The official Developer plan is free but limited to development/testing, has a 24-hour delay, searches only up to one month back, and has a daily request cap. It is not permitted for production/staging use under that plan. | Implement behind an optional API-key adapter. Use only in a local development environment unless the project has an appropriate paid plan. Do not make the public demo depend on the free Developer plan. |
| Existing `news_vs_market_2020/news_sentiment_raw.csv` + market prices | Supplementary market-level experiments and coverage comparison | 11,395 articles; reported dates 2020-03-16 to 2026-10-08; no company links; uneven monthly counts | Keep for broad market-context tests only. Existing sentiment appears to be generic VADER. Derived files are not separate raw sources. |
| Existing `news_aspect_sentiment/SEntFiN-v1.1.csv` | Optional labelled evaluation set | 10,753 headlines with entity-level labels, no timestamps/tickers | Use for entity/sentiment evaluation only after parsing and terms are checked; not a historical time series. |
| Existing Financial PhraseBank files | Optional sentiment evaluation/baseline | Four agreement-level sentence sets; no dates/tickers | The local `License.txt` and `README.txt` must be followed. Do not redistribute raw files without confirming permission. Avoid reporting evaluation on examples potentially seen during model training. |
| Existing `market_events_2025/financial_news_events.csv` / `.json` | Event taxonomy and rule testing | 3,024 rows but only 50 unique headlines; 2025-02-01 to 2025-08-14 | Treat as potentially templated/synthetic until provenance is confirmed. Do not use as evidence of live coverage; CSV/JSON may duplicate each other. |
| `tweets_returns` | None in initial pipeline | Reduced file has malformed/misaligned records and implausible parsed dates | Exclude; preserve raw files unchanged. |
| yfinance | Price reference for Module A and optional market context | Symbol/availability and service terms may vary | Record retrieval date and limitations; do not describe it as an official exchange feed. |

### Historical and recent coverage strategy

Use three separate modes:
1. **Historical replay/backtest:** 2021-09-30 through 2022-09-29, aligned to existing tweets and prices.
2. **Historical news:** use the existing historical social dataset for the reproducible backtest. FNSPID is optional only because the tested mirror covered three of the 16 selected tickers.
3. **Recent inference:** GDELT first; NewsAPI only when a valid key and permitted plan are available.

These sources do not automatically produce continuous 2021–present coverage. Report observed coverage and gaps rather than implying completeness.

## 3. FNSPID adoption and data-handling rules

Reference links:
- Repository and download instructions: https://github.com/Zdong104/FNSPID_Financial_News_Dataset
- Dataset paper: https://arxiv.org/abs/2402.06698
- News CSV advertised by the repository: https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv

FNSPID extraction was attempted via a JSONL mirror to avoid downloading the 23.2 GB CSV. The resulting subset contained only AAPL, AMD, and AMZN, so FNSPID is deferred as a required source. Preserve `data/raw/fnspid/fnspid_selected_news.csv` for optional experiments; do not commit it unless repository data policy and dataset terms permit it. Do not retry full-file scans under the current time constraints.

**Terms caution:** the repository's README contains both a 2025 note saying commercial and research rights are released and older disclaimer text restricting commercial use. The repository also has a separate `LICENSE` file. Treat the rights as **not fully resolved** until the actual license file and dataset terms are checked together. For the hackathon prototype, use the dataset locally, cite the paper/source, and do not redistribute the raw dataset or article text in the public repository.

Suggested paper citation:
Dong, Z., Fan, X., & Peng, Z. (2024). *FNSPID: A Comprehensive Financial News Dataset in Time Series*. arXiv:2402.06698.

## 4. GDELT and NewsAPI adapter rules

### GDELT
- DOC API endpoint: `https://api.gdeltproject.org/api/v2/doc/doc`
- Use JSON article-list responses and a bounded query/window.
- Preserve article URL, title, domain, language/country when returned, seen date, retrieval timestamp, and query.
- Use a timeout, small page/request volume, and retry only a limited number of times.
- The DOC API is for recent discovery and is not the historical archive for 2021–2023.
- Deduplicate repeated results by canonical URL and normalized title.

### NewsAPI.org
- Endpoint: `https://newsapi.org/v2/everything`
- Keep `NEWSAPI_API_KEY` in `.env`; never hard-code or commit the key.
- Use only in local development/testing on the free Developer plan.
- If the hosted/public demo needs it, obtain a plan that explicitly permits that deployment or disable the adapter in the hosted environment.
- Store the article URL and metadata; do not assume the API grants redistribution rights to full article content.
- Respect the plan's request quota and terms.

## 5. Downstream modules

Both modules are required.

### Module A — Tactical Index Rebalancer
- Use a mock universe of 10–20 eligible S&P 100 constituents.
- For the first backtest, prefer names with usable historical tweet and price coverage.
- Record the S&P 100 membership reference date and ticker aliases in `config/tickers.yaml`.
- Use company-specific aggregated signals to adjust weights; apply broad-market signals only through explicit, documented rules.
- Enforce max/min weights and verify that weights sum to 1.0.

### Module B — Strategic Portfolio Stress Tester
- Use a synthetic portfolio with documented loans, bonds, and derivatives.
- Map event categories and impact thresholds to transparent asset-class shocks.
- Permit event/market signals to trigger tests without a ticker.
- Show portfolio value before/after shocks and contributions by asset class.
- Label all asset values and shock rules as simulation assumptions, not real bank risk estimates.

## 6. Licensing, attribution and public repository

Do not commit raw datasets, API responses containing article text, credentials, or large downloaded files unless the applicable terms clearly permit it. Commit code, source URLs, documentation, small generated examples that are safe to redistribute, and scripts that allow reviewers to reproduce the workflow.

| Source | Status | Required action |
|---|---|---|
| Stock tweets dataset | Terms not yet verified locally | Check original dataset card; do not redistribute raw data without permission. |
| FNSPID | Terms require reconciliation between repository README and `LICENSE` | Inspect the actual license and dataset card; cite the paper; keep raw files out of Git. |
| GDELT DOC API | Official API terms/usage guidance must be reviewed before release | Preserve provenance; rate-limit requests; avoid bulk redistribution of article text. |
| NewsAPI.org | Plan-specific; free Developer plan is development/testing only | Keep optional and disabled for production unless a suitable plan is available. |
| Financial PhraseBank | Local `License.txt` and `README.txt` available | Follow included terms and verify provenance/model overlap before evaluation or redistribution. |
| SEntFiN | Terms not yet verified | Check original dataset/paper and attribution requirements. |
| `news_vs_market_2020` | Terms not yet verified | Check dataset card and underlying article/source terms. |
| `financial_news_events` | Provenance/terms not yet verified | Confirm origin and whether rows are synthetic or templated. |
| yfinance | Applicable provider/service terms should be reviewed | Document limitations and retrieval date. |

## 7. Phase 1 checklist

- [x] Profile existing local datasets and create `docs/notes/dataset_profiles.md`.
- [x] Exclude malformed `tweets_returns` data from the initial pipeline.
- [x] Set the initial historical replay window to 2021-09-30 through 2022-09-29.
- [x] Confirm both Module A and Module B are in scope.
- [x] Allow company, event, and market scopes.
- [x] Defer FNSPID as a required source because the tested mirror did not cover 13 of 16 selected tickers.
- [x] Select GDELT as the primary recent-news adapter candidate.
- [x] Select NewsAPI as an optional adapter, not a required hosted-demo dependency on the free plan.
- [x] Profile the FNSPID mirror subset: 18,483 rows, only AAPL/AMD/AMZN, date span 2021-01-04 to 2023-12-31; deferred as a required source.
- [ ] Finalize and document the 10–20-stock universe and membership reference date.
- [ ] Fetch and validate prices for the approved universe plus benchmark.
- [ ] Implement and test canonical ingestion adapters for FNSPID, GDELT and optional NewsAPI.
- [ ] Implement the risk engine, then both downstream modules and the dashboard.
- [ ] Confirm applicable terms before publishing any data; rerun tests and profile coverage after integration.

**Implementation priority:** implement GDELT first and NewsAPI second behind a shared normalized schema; use the existing historical tweet/price data for backtesting. Keep the partial FNSPID subset optional, not required. Then connect the feeds to the risk engine and both downstream modules.
