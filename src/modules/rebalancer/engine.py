from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MOCK_INDEX_TICKERS = [
    "TSLA", "AAPL", "MSFT", "AMD", "INTC", "CRM", "AMZN", "GOOG",
    "META", "NFLX", "DIS", "VZ", "PG", "KO", "COST", "BA",
]


def load_price_panel(path: str | Path) -> pd.DataFrame:
    """Return close prices indexed by date, with one column per ticker."""
    frame = pd.read_csv(path)
    required = {"date", "ticker", "close"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Price CSV must contain columns: {sorted(required)}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "ticker", "close"])
    frame = frame[frame["close"] > 0]
    if frame.empty:
        raise ValueError("No valid price rows found")
    panel = frame.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
    panel = panel.sort_index().sort_index(axis=1)
    panel = panel.dropna(axis=1, thresh=max(2, int(len(panel) * 0.8)))
    if panel.shape[1] < 2 or panel.shape[0] < 3:
        raise ValueError("Need at least two tickers and three dates for a backtest")
    return panel


def load_signals_from_db(db_path: str | Path) -> pd.DataFrame:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Signal database not found: {path}")
    with sqlite3.connect(str(path)) as conn:
        frame = pd.read_sql_query(
            "SELECT timestamp, ticker, scope, sentiment, confidence, impact, event_type "
            "FROM signals WHERE scope = 'company'",
            conn,
        )
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "ticker", "scope", "sentiment", "confidence", "impact", "event_type"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    for col in ("sentiment", "confidence", "impact"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "ticker", "sentiment", "confidence"])
    frame = frame[(frame["ticker"] != "MARKET") & frame["sentiment"].between(-1, 1) & frame["confidence"].between(0, 1)]
    return frame.sort_values("timestamp").reset_index(drop=True)


def _cap_and_normalize(target: np.ndarray, max_weight: float) -> np.ndarray:
    if max_weight <= 0 or max_weight * len(target) < 1 - 1e-9:
        raise ValueError("max_weight must be positive and at least 1 / number of tickers")
    target = np.maximum(target, 0.0)
    if target.sum() <= 0:
        target = np.ones_like(target)
    target = target / target.sum()
    result = np.zeros_like(target)
    free = np.ones(len(target), dtype=bool)
    remaining = 1.0
    while free.any():
        free_total = target[free].sum()
        proposal = np.full(free.sum(), remaining / free.sum()) if free_total <= 0 else target[free] / free_total * remaining
        free_idx = np.flatnonzero(free)
        over = proposal > max_weight + 1e-12
        if not over.any():
            result[free_idx] = proposal
            break
        capped_idx = free_idx[over]
        result[capped_idx] = max_weight
        remaining -= max_weight * len(capped_idx)
        free[capped_idx] = False
        target[capped_idx] = 0.0
    return result / result.sum()


def _prepare_signal_index(
    signals: pd.DataFrame,
    tickers: list[str],
    min_confidence: float,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Index sorted per-ticker signal arrays so each daily lookup stays small."""
    if signals.empty:
        return {}
    eligible = signals[
        signals["ticker"].isin(tickers) & (signals["confidence"] >= min_confidence)
    ].sort_values("timestamp")
    indexed: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for ticker, group in eligible.groupby("ticker", sort=False):
        indexed[str(ticker)] = (
            group["timestamp"].map(lambda ts: pd.Timestamp(ts).value).to_numpy(dtype=np.int64),
            group["sentiment"].to_numpy(dtype=float),
            group["confidence"].to_numpy(dtype=float),
        )
    return indexed


def _sentiment_by_ticker(
    signal_index: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
    as_of: date,
    tickers: list[str],
    *,
    lookback_days: int,
    half_life_hours: float,
) -> dict[str, float]:
    result = {ticker: 0.0 for ticker in tickers}
    end_ns = pd.Timestamp(as_of, tz="UTC").value
    cutoff_ns = pd.Timestamp(as_of - timedelta(days=lookback_days), tz="UTC").value
    for ticker in tickers:
        values = signal_index.get(ticker)
        if values is None:
            continue
        timestamps, sentiments, confidences = values
        left = int(np.searchsorted(timestamps, cutoff_ns, side="left"))
        right = int(np.searchsorted(timestamps, end_ns, side="left"))
        if right <= left:
            continue
        selected_times = timestamps[left:right]
        age_hours = np.maximum(0.0, (end_ns - selected_times) / 3_600_000_000_000.0)
        weights = confidences[left:right] * np.power(0.5, age_hours / half_life_hours)
        total_weight = float(weights.sum())
        if total_weight > 0:
            result[ticker] = float(np.clip(np.dot(sentiments[left:right], weights) / total_weight, -1.0, 1.0))
    return result


def backtest_rebalancer(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    lookback_days: int = 7,
    min_confidence: float = 0.5,
    half_life_hours: float = 48.0,
    max_tilt: float = 0.5,
    max_weight: float = 0.15,
    turnover_limit: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build daily weights and compare sentiment-tilted returns to static equal weight.

    Signals published on a date are not used for that date's rebalance. Today's
    weights earn the following close-to-close return, preventing same-day lookahead.
    Turnover is one-way turnover: half the sum of absolute weight changes.
    """
    if lookback_days < 1 or half_life_hours <= 0:
        raise ValueError("lookback_days and half_life_hours must be positive")
    if not 0 <= min_confidence <= 1 or not 0 <= max_tilt <= 1 or not 0 < turnover_limit <= 1:
        raise ValueError("Invalid confidence, tilt, or turnover parameter")
    tickers = list(prices.columns)
    if not tickers:
        raise ValueError("No tickers available")
    if max_weight * len(tickers) < 1 - 1e-9:
        raise ValueError(f"max_weight={max_weight} is too low for {len(tickers)} tickers")
    prices = prices.sort_index().copy()
    returns = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    signal_index = _prepare_signal_index(signals, tickers, min_confidence)
    equal = np.full(len(tickers), 1.0 / len(tickers))
    previous = equal.copy()
    weight_records: list[dict[str, Any]] = []
    daily_records: list[dict[str, Any]] = []
    prior_weights = equal.copy()
    for idx, day in enumerate(prices.index):
        sentiments = _sentiment_by_ticker(
            signal_index, day, tickers, lookback_days=lookback_days,
            half_life_hours=half_life_hours,
        )
        raw = np.asarray([1.0 / len(tickers) * (1.0 + max_tilt * sentiments[t]) for t in tickers], dtype=float)
        target = _cap_and_normalize(raw, max_weight=max_weight)
        if idx == 0:
            weights = equal.copy()
            turnover = 0.0
        else:
            one_way_turnover = float(0.5 * np.abs(target - previous).sum())
            scale = min(1.0, turnover_limit / one_way_turnover) if one_way_turnover > 0 else 1.0
            weights = previous + scale * (target - previous)
            weights = weights / weights.sum()
            turnover = float(0.5 * np.abs(weights - previous).sum())
        for ticker, weight in zip(tickers, weights):
            weight_records.append({"date": day.isoformat(), "ticker": ticker, "weight": float(weight), "signal_sentiment": sentiments[ticker]})
        if idx == 0:
            strategy_return = 0.0
            equal_return = 0.0
        else:
            # Prior day's weights earn today's close-to-close returns.
            today_returns = returns.iloc[idx].reindex(tickers).to_numpy(dtype=float)
            strategy_return = float(np.dot(prior_weights, today_returns))
            equal_return = float(np.dot(equal, today_returns))
        daily_records.append({
            "date": day.isoformat(),
            "strategy_return": strategy_return,
            "equal_weight_return": equal_return,
            "strategy_value": np.nan,
            "equal_weight_value": np.nan,
            "one_way_turnover": turnover,
        })
        prior_weights = weights.copy()
        previous = weights.copy()
    daily = pd.DataFrame(daily_records)
    daily["strategy_value"] = (1.0 + daily["strategy_return"]).cumprod()
    daily["equal_weight_value"] = (1.0 + daily["equal_weight_return"]).cumprod()
    return pd.DataFrame(weight_records), daily


def performance_summary(daily: pd.DataFrame) -> dict[str, float]:
    if daily.empty:
        return {}
    results: dict[str, float] = {}
    portfolio_columns = [("strategy", "strategy_return"), ("equal_weight", "equal_weight_return")]
    if "spy_return" in daily.columns:
        portfolio_columns.append(("spy", "spy_return"))
    for name, col in portfolio_columns:
        values = daily[col].astype(float)
        cumulative = float((1.0 + values).prod() - 1.0)
        volatility = float(values.std(ddof=1) * np.sqrt(252)) if len(values) > 1 else 0.0
        sharpe = float(values.mean() / values.std(ddof=1) * np.sqrt(252)) if len(values) > 1 and values.std(ddof=1) > 0 else 0.0
        drawdown = (1.0 + values).cumprod() / (1.0 + values).cumprod().cummax() - 1.0
        results[f"{name}_cumulative_return"] = cumulative
        results[f"{name}_annualized_volatility"] = volatility
        results[f"{name}_sharpe_zero_rf"] = sharpe
        results[f"{name}_max_drawdown"] = float(drawdown.min())
    results["total_one_way_turnover"] = float(daily["one_way_turnover"].sum())
    return results


def add_spy_benchmark(daily: pd.DataFrame, spy_prices: pd.Series, dates: pd.Index) -> pd.DataFrame:
    """Attach a SPY buy-and-hold return series aligned to the backtest dates."""
    result = daily.copy()
    aligned = spy_prices.reindex(dates).astype(float)
    returns = aligned.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    result["spy_return"] = returns.to_numpy(dtype=float)
    result["spy_value"] = (1.0 + result["spy_return"]).cumprod()
    return result
