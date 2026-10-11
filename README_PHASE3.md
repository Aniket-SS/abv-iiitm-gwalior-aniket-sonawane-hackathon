# Phase 3 — NLP Risk Engine

## What Phase 3 adds

Phase 3 turns normalized `Document` records into validated `Signal` records. It keeps the Phase 0 schema stable and does not call live APIs.

- `src/engine/preprocessing.py`: markup and whitespace normalization while preserving financial terms, numbers, cashtags, and negation.
- `src/engine/entity_linking.py`: uses the Phase 2 conservative alias matcher and optional spaCy NER. NER is supporting evidence; it cannot override the ambiguous-name rules.
- `src/engine/sentiment.py`: FinBERT (`ProsusAI/finbert`) sentiment score as positive probability minus negative probability. In `auto` mode, it falls back to a deterministic lexicon if the model package/download is unavailable.
- `src/engine/event_classifier.py`: zero-shot classification using `facebook/bart-large-mnli` and the configured taxonomy. In `auto` mode, a taxonomy-keyword baseline is used if the model is unavailable.
- `src/engine/impact.py`: explainable rule-based severity starting from each event class's `base_severity`, then adjusting for high-severity terms, sentiment magnitude, and event confidence. This is a heuristic, not calibrated loss prediction.
- `src/engine/pipeline.py`: orchestrates the components and creates one `Signal` per linked ticker.
- `scripts/run_engine.py`: JSONL input/output CLI.
- `scripts/evaluate_engine.py`: sentiment evaluation against SEntFiN entity-level labels or the two-column `all-data.csv` format.
- `tests/test_engine_phase3.py`: offline tests for preprocessing, entity linking, sentiment fallback, taxonomy classification, impact, and signal contracts.

## Market/event signals without a company ticker

Every `Signal` has a `scope` label: `company` or `market`. The field defaults to `company` to preserve compatibility with existing constructors and tests. Company signals carry a real ticker; unlinked news can produce `ticker="MARKET"`, `scope="market"`, and `company=null` so Module B can consume systemic events without invented company links. Unlinked social posts are skipped rather than automatically classified as market-wide. Module A must exclude `MARKET`; Module B may consume market-wide signals and company-specific signals for asset-specific shocks.

## PowerShell quickstart

Run these commands from the repository root in PowerShell. Python 3.11 is recommended for the smoothest dependency compatibility.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
python -m scripts.run_engine data/sample/phase3_documents.jsonl --mode rules --no-spacy --output data/processed/phase3_signals.jsonl
```

`--mode rules` avoids transformer model downloads and is suitable for a smoke test. For model inference, use:

```powershell
python -m scripts.run_engine data/processed/ingestion/documents.jsonl --mode auto --output data/processed/signals.jsonl
```

In `auto` mode the script attempts to load the configured Hugging Face models and falls back if unavailable. The first model run may download large model files. Install the spaCy English model if you want NER support:

```powershell
python -m spacy download en_core_web_sm
```

Alias matching works without the spaCy model. Do not commit model caches or `.env`.

## Sentiment evaluation

The two datasets are evaluation resources, not live ingestion feeds. SEntFiN stores entity sentiment in the `Decisions` JSON field; the evaluator appends the entity name to its headline context. `all-data.csv` is expected to have `label,text` columns. Use local paths and keep raw dataset files out of the public repository unless redistribution terms permit them.

```powershell
python -m scripts.evaluate_engine --dataset sentfin --input data/raw/news_aspect_sentiment/SEntFiN-v1.1.csv --mode auto --limit 500
python -m scripts.evaluate_engine --dataset all-data --input data/raw/news_headlines_sentiment/all-data.csv --mode auto --limit 1000
```

Evaluation metrics are sentiment-only. Do not treat them as out-of-sample evidence if the labeled dataset overlaps with the model's training data. Event classification and impact calibration are separate tasks; impact calibration is planned for Phase 5.

## Limitations

- A fallback result is useful for deterministic local development, but it is not equivalent to the configured pretrained models.
- A news story can discuss multiple companies; the engine emits one signal per linked ticker, with the same text-level sentiment/event score for each.
- No ticker is guessed from general market context. Unlinked news receives `ticker="MARKET"` and `scope="market"`; unlinked social posts are skipped. `scope` defaults to `company` for backwards compatibility.
- `confidence` combines sentiment and event-classifier confidence; it is not a calibrated probability that a market move will occur.
- Model output and impact rules need empirical evaluation and Phase 5 calibration before financial-performance claims are made.

## Initial evaluation baseline (offline fallback)

The evaluator was run over the full locally supplied labels using `--mode lexicon` because `transformers` was not installed in the test runtime. These are **lexicon-baseline smoke/evaluation results, not FinBERT results**:

| Dataset | Evaluated labels | Accuracy | Macro F1 |
|---|---:|---:|---:|
| SEntFiN entity-level `Decisions` | 14,409 | 0.5218 | 0.4786 |
| `all-data.csv` | 4,846 | 0.6523 | 0.4751 |

The SEntFiN score is computed per `(headline, entity label)` pair; the entity name is appended to the headline as context. The all-data set is class-imbalanced toward neutral examples, so accuracy alone is misleading. The baseline overpredicts neutral and has weaker positive/negative F1. Install the Phase 3 requirements and rerun with `--mode auto` to evaluate the pretrained model. Check dataset/model overlap before describing these metrics as out-of-sample performance.
