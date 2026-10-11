"""Exploratory event-study utilities for Phase 5 impact calibration.

The calibration is descriptive: it compares existing impact scores with later
price movements. It does not retrain the NLP engine or alter stored signals.
"""
from __future__ import annotations

import csv
import math
import sqlite3
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_prices(path: str | Path) -> dict[str, dict[date, float]]:
    """Load long-form prices or the project's Stock Name/Adj Close CSV.

    Supported columns:
      * date,ticker,close (output of scripts.fetch_prices)
      * Date,Stock Name,Close,Adj Close (stock_yfinance_data)

    A market_prices.csv containing spy_close/qqq_close/dia_close is supported too.
    """
    path = Path(path)
    prices: dict[str, dict[date, float]] = defaultdict(dict)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"Price file has no header: {path}")
        fields = {name.strip().casefold(): name for name in reader.fieldnames}
        date_col = fields.get("date")
        ticker_col = fields.get("ticker") or fields.get("stock name")
        close_col = fields.get("adj close") or fields.get("close")
        benchmark_cols = {
            ticker: fields.get(f"{ticker.casefold()}_close")
            for ticker in ("SPY", "QQQ", "DIA")
        }
        if date_col and ticker_col and close_col:
            for row in reader:
                try:
                    day = date.fromisoformat(row[date_col].strip()[:10])
                except (AttributeError, ValueError):
                    continue
                ticker = (row.get(ticker_col) or "").strip().upper()
                close = _number(row.get(close_col))
                if ticker and close is not None and close > 0:
                    prices[ticker][day] = close
        elif date_col and any(benchmark_cols.values()):
            for row in reader:
                try:
                    day = date.fromisoformat(row[date_col].strip()[:10])
                except (AttributeError, ValueError):
                    continue
                for ticker, column in benchmark_cols.items():
                    if column:
                        close = _number(row.get(column))
                        if close is not None and close > 0:
                            prices[ticker][day] = close
        else:
            raise ValueError(
                "Unsupported price columns. Expected date/ticker/close, "
                "Date/Stock Name/Adj Close, or date with spy_close/qqq_close/dia_close."
            )
    return {ticker: dict(sorted(series.items())) for ticker, series in prices.items()}


def _rank(values: list[float]) -> list[float]:
    """Average ranks for ties, without requiring scipy."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        average = ((i + 1) + j) / 2
        for k in range(i, j):
            ranks[order[k]] = average
        i = j
    return ranks


def _pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2 or len(x) != len(y):
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    dx, dy = [v - mx for v in x], [v - my for v in y]
    denom = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    return sum(a * b for a, b in zip(dx, dy)) / denom if denom else None


def spearman(x: Iterable[float], y: Iterable[float]) -> float | None:
    x_values, y_values = list(x), list(y)
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None
    return _pearson(_rank(x_values), _rank(y_values))


def load_signals_from_sqlite(db_path: str | Path) -> list[dict[str, Any]]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Signal database not found: {path}")
    with sqlite3.connect(str(path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT signal_id, timestamp, ticker, scope, impact, confidence, sentiment, event_type, channel "
            "FROM signals ORDER BY timestamp, signal_id"
        ).fetchall()
    return [dict(row) for row in rows]


def event_study(
    signals: Iterable[dict[str, Any]],
    prices: dict[str, dict[date, float]],
    *,
    benchmark: str = "SPY",
    horizons: tuple[int, ...] = (1, 3, 5),
) -> list[dict[str, Any]]:
    """Match signals to the first trading close strictly after the event date.

    Using the event date's close can leak a price move that happened before a
    signal published after market close. Daily data cannot resolve intraday
    publication time, so this conservative policy starts at the first close after
    the event date and measures returns over the following trading sessions.
    Company abnormal return is stock return minus benchmark return; market-scope
    signals use the benchmark's own return as the outcome.
    """
    if not horizons or any(h < 1 for h in horizons):
        raise ValueError("horizons must contain positive trading-day integers")
    dates_by_ticker = {ticker: sorted(series) for ticker, series in prices.items()}
    output: list[dict[str, Any]] = []
    for signal in signals:
        try:
            stamp = datetime.fromisoformat(str(signal["timestamp"]).replace("Z", "+00:00"))
            event_day = stamp.date()
            impact = float(signal["impact"])
            confidence = float(signal.get("confidence", 0.0))
            ticker = str(signal["ticker"]).upper()
            scope = str(signal.get("scope", "company"))
        except (KeyError, TypeError, ValueError):
            continue
        outcome_ticker = benchmark if scope == "market" or ticker == "MARKET" else ticker
        series = prices.get(outcome_ticker)
        dates = dates_by_ticker.get(outcome_ticker, [])
        if not series or not dates:
            continue
        if event_day < dates[0]:
            continue
        start_idx = bisect_right(dates, event_day)
        if start_idx >= len(dates):
            continue
        start_day = dates[start_idx]
        start_close = series[start_day]
        row: dict[str, Any] = {
            "signal_id": signal.get("signal_id", ""),
            "timestamp": str(signal.get("timestamp", "")),
            "event_date": event_day.isoformat(),
            "matched_price_date": start_day.isoformat(),
            "ticker": ticker,
            "outcome_ticker": outcome_ticker,
            "scope": scope,
            "event_type": signal.get("event_type", "other"),
            "channel": signal.get("channel", "unknown"),
            "impact": impact,
            "confidence": confidence,
            "sentiment": float(signal.get("sentiment", 0.0)),
        }
        for horizon in horizons:
            end_idx = start_idx + horizon
            key = f"{horizon}d"
            if end_idx >= len(dates):
                row[f"forward_return_pct_{key}"] = None
                row[f"benchmark_return_pct_{key}"] = None
                row[f"abnormal_return_pct_{key}"] = None
                continue
            end_day = dates[end_idx]
            forward_return = (series[end_day] / start_close - 1.0) * 100.0
            if scope == "market" or ticker == "MARKET":
                benchmark_return = 0.0
                abnormal_return = forward_return
            else:
                benchmark_series = prices.get(benchmark, {})
                benchmark_dates = dates_by_ticker.get(benchmark, [])
                bench_start_idx = bisect_left(benchmark_dates, start_day)
                bench_end_idx = bisect_left(benchmark_dates, end_day)
                if (bench_start_idx >= len(benchmark_dates) or bench_end_idx >= len(benchmark_dates)
                        or benchmark_dates[bench_start_idx] != start_day
                        or benchmark_dates[bench_end_idx] != end_day):
                    benchmark_return = None
                    abnormal_return = None
                else:
                    bench_start = benchmark_series[benchmark_dates[bench_start_idx]]
                    bench_end = benchmark_series[benchmark_dates[bench_end_idx]]
                    benchmark_return = (bench_end / bench_start - 1.0) * 100.0
                    abnormal_return = forward_return - benchmark_return
            row[f"forward_return_pct_{key}"] = round(forward_return, 6)
            row[f"benchmark_return_pct_{key}"] = round(benchmark_return, 6) if benchmark_return is not None else None
            row[f"abnormal_return_pct_{key}"] = round(abnormal_return, 6) if abnormal_return is not None else None
        output.append(row)
    return output


def summarize_calibration(rows: list[dict[str, Any]], horizon: int = 3) -> dict[str, Any]:
    key = f"{horizon}d"
    usable = [row for row in rows if row.get(f"abnormal_return_pct_{key}") is not None]
    if not usable:
        return {"horizon_trading_days": horizon, "matched_signals": 0, "impact_vs_abs_abnormal_return_spearman": None, "bands": []}
    impacts = [float(row["impact"]) for row in usable]
    outcomes = [abs(float(row[f"abnormal_return_pct_{key}"])) for row in usable]
    bands = [(1, 3, "1-3"), (4, 6, "4-6"), (7, 8, "7-8"), (9, 10, "9-10")]
    band_rows = []
    for low, high, label in bands:
        selected = [row for row in usable if low <= float(row["impact"]) <= high]
        values = [abs(float(row[f"abnormal_return_pct_{key}"])) for row in selected]
        if selected:
            band_rows.append({
                "impact_band": label,
                "count": len(selected),
                "mean_abs_abnormal_return_pct": round(sum(values) / len(values), 6),
                "median_abs_abnormal_return_pct": round(sorted(values)[len(values) // 2], 6),
            })
        else:
            band_rows.append({"impact_band": label, "count": 0, "mean_abs_abnormal_return_pct": None, "median_abs_abnormal_return_pct": None})
    return {
        "horizon_trading_days": horizon,
        "matched_signals": len(usable),
        "impact_vs_abs_abnormal_return_spearman": round(spearman(impacts, outcomes), 6) if spearman(impacts, outcomes) is not None else None,
        "mean_abs_abnormal_return_pct": round(sum(outcomes) / len(outcomes), 6),
        "bands": band_rows,
        "interpretation": "Exploratory association only; not causal evidence or proof of predictive performance.",
    }
