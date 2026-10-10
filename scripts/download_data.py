"""Download the Kaggle datasets for Phase 1 into data/raw/<name>/.

Run from the repository root:
    python -m scripts.download_data                 # everything
    python -m scripts.download_data --only stock_tweets news_vs_market_2020
    python -m scripts.download_data --force         # re-download even if present

Uses `kagglehub`. Public datasets usually need no login; if Kaggle asks for credentials,
put KAGGLE_USERNAME and KAGGLE_KEY in your .env (see .env.example).

The two large transaction datasets (Module B inspiration) are intentionally NOT here;
they are only needed in Phase 7.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from src.common.config import get_settings, resolve_path  # also loads .env
from src.common.logging_utils import get_logger

log = get_logger("download_data")

# local folder name -> Kaggle "owner/dataset" slug
DATASETS: dict[str, str] = {
    "news_headlines_sentiment": "ankurzing/sentiment-analysis-for-financial-news",
    "news_aspect_sentiment": "ankurzing/aspect-based-sentiment-analysis-for-financial-news",
    "market_events_2025": "pratyushpuri/financial-news-market-events-dataset-2025",
    "news_vs_market_2020": "belbino/financial-news-sentiment-vs-market-2020-present",
    "tweets_returns": "thedevastator/tweet-sentiment-s-impact-on-stock-returns",
    "stock_tweets": "equinxx/stock-tweets-for-sentiment-analysis-and-prediction",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--only", nargs="*", choices=sorted(DATASETS), help="download just these")
    parser.add_argument("--force", action="store_true", help="re-download existing datasets")
    args = parser.parse_args()

    import kagglehub  # imported late so --help works without the package

    raw_root = resolve_path(get_settings().paths.data_raw)
    failed: list[str] = []

    for name, slug in DATASETS.items():
        if args.only and name not in args.only:
            continue
        dest = raw_root / name
        if dest.exists() and any(dest.iterdir()) and not args.force:
            log.info("skip %-26s (already in %s)", name, dest)
            continue
        log.info("downloading %s ...", slug)
        try:
            cache_path = Path(kagglehub.dataset_download(slug))
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cache_path, dest, dirs_exist_ok=True)
            log.info("saved   %-26s -> %s", name, dest)
        except Exception as exc:  # noqa: BLE001 - we want to continue with the others
            failed.append(name)
            log.error("FAILED  %s: %s", name, exc)
            log.error("        manual fallback: download from https://www.kaggle.com/datasets/%s "
                      "and unzip into %s", slug, dest)

    if failed:
        log.warning("Failed: %s", ", ".join(failed))
    else:
        log.info("All requested datasets are in %s", raw_root)


if __name__ == "__main__":
    main()
