from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.modules.rebalancer.engine import (
    backtest_rebalancer,
    load_price_panel,
    load_signals_from_db,
    performance_summary,
    MOCK_INDEX_TICKERS,
    add_spy_benchmark,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest sentiment-tilted index rebalancing against static equal weight.")
    parser.add_argument("--prices", default=str(ROOT / "data/raw/prices/prices_daily.csv"))
    parser.add_argument("--db", default=str(ROOT / "data/processed/signals.db"))
    parser.add_argument("--output-dir", default=str(ROOT / "data/processed/phase6"))
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--max-tilt", type=float, default=0.5)
    parser.add_argument("--max-weight", type=float, default=0.15)
    parser.add_argument("--turnover-limit", type=float, default=0.10)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_prices = load_price_panel(args.prices)
    missing = sorted(set(MOCK_INDEX_TICKERS) - set(all_prices.columns))
    if missing:
        raise ValueError(f"Mock index tickers missing from price data: {missing}")
    prices = all_prices[MOCK_INDEX_TICKERS].copy()
    spy_prices = all_prices["SPY"].copy() if "SPY" in all_prices.columns else None
    signals = load_signals_from_db(args.db)
    weights, daily = backtest_rebalancer(
        prices, signals,
        lookback_days=args.lookback_days,
        min_confidence=args.min_confidence,
        max_tilt=args.max_tilt,
        max_weight=args.max_weight,
        turnover_limit=args.turnover_limit,
    )
    weights.to_csv(output_dir / "weights_over_time.csv", index=False)
    daily.to_csv(output_dir / "performance_comparison.csv", index=False)
    if spy_prices is not None:
        daily = add_spy_benchmark(daily, spy_prices, prices.index)
        daily.to_csv(output_dir / "performance_comparison.csv", index=False)
    summary = performance_summary(daily)
    (output_dir / "performance_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Mock index tickers: {len(prices.columns)}")
    print(f"SPY benchmark: {'enabled' if spy_prices is not None else 'not available'}")
    print(f"Price dates: {len(prices)} ({prices.index[0]} through {prices.index[-1]})")
    print(f"Company signals loaded: {len(signals):,}")
    print(f"Weights: {output_dir / 'weights_over_time.csv'}")
    print(f"Performance: {output_dir / 'performance_comparison.csv'}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
