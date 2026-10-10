"""Download daily OHLCV prices (yfinance) for the ticker universe + a benchmark.

    python -m scripts.fetch_prices --start 2019-01-01
    python -m scripts.fetch_prices --start 2021-09-01 --end 2022-10-01 --benchmark SPY

Output: data/raw/prices/prices_daily.csv with columns
    date, ticker, open, high, low, close, volume
Prices are split/dividend adjusted (auto_adjust=True). The benchmark (default SPY) is used
later to compute abnormal returns for impact calibration.
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd

from src.common.config import get_settings, get_tickers, resolve_path
from src.common.logging_utils import get_logger

log = get_logger("fetch_prices")
FIELDS = ["open", "high", "low", "close", "volume"]


def to_long(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Convert yfinance's wide (ticker, field) frame into a tidy long frame."""
    frames = []
    for t in tickers:
        if isinstance(raw.columns, pd.MultiIndex):
            if t not in raw.columns.get_level_values(0):
                log.warning("no data returned for %s", t)
                continue
            sub = raw[t].copy()
        else:  # single-ticker download
            sub = raw.copy()
        sub.columns = [str(c).lower() for c in sub.columns]
        sub = sub.dropna(subset=["close"])
        if sub.empty:
            log.warning("no price rows for %s", t)
            continue
        sub = sub[[c for c in FIELDS if c in sub.columns]]
        sub.insert(0, "ticker", t)
        sub.index.name = "date"
        frames.append(sub.reset_index())
    if not frames:
        raise RuntimeError("yfinance returned no usable data")
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out.sort_values(["ticker", "date"]).reset_index(drop=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--start", default="2019-01-01")
    p.add_argument("--end", default=date.today().isoformat(), help="exclusive end date")
    p.add_argument("--benchmark", default="SPY", help="market proxy for abnormal returns")
    args = p.parse_args()

    import yfinance as yf  # imported late so the module is importable without it

    tickers = list(get_tickers())
    symbols = tickers + ([args.benchmark] if args.benchmark not in tickers else [])
    log.info("downloading %d symbols %s -> %s", len(symbols), args.start, args.end)

    raw = yf.download(symbols, start=args.start, end=args.end, auto_adjust=True,
                      progress=False, group_by="ticker", threads=True)
    long_df = to_long(raw, symbols)

    out_dir = resolve_path(get_settings().paths.data_raw) / "prices"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "prices_daily.csv"
    long_df.to_csv(out_path, index=False)

    summary = long_df.groupby("ticker")["date"].agg(["min", "max", "count"])
    log.info("saved %s\n%s", out_path, summary.to_string())


if __name__ == "__main__":
    main()
