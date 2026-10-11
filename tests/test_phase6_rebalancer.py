from datetime import date

import numpy as np
import pandas as pd

from src.modules.rebalancer.engine import backtest_rebalancer, performance_summary


def test_rebalancer_weights_sum_to_one_and_turnover_is_capped():
    dates = [date(2024, 1, d) for d in range(2, 8)]
    prices = pd.DataFrame(
        {"AAA": [100, 101, 99, 102, 103, 104], "BBB": [100, 99, 101, 100, 99, 102]},
        index=dates,
    )
    signals = pd.DataFrame([
        {"timestamp": pd.Timestamp("2024-01-02T12:00:00Z"), "ticker": "AAA", "scope": "company", "sentiment": 1.0, "confidence": 0.95, "impact": 8.0, "event_type": "earnings"},
        {"timestamp": pd.Timestamp("2024-01-02T12:00:00Z"), "ticker": "BBB", "scope": "company", "sentiment": -1.0, "confidence": 0.95, "impact": 8.0, "event_type": "earnings"},
    ])
    weights, daily = backtest_rebalancer(prices, signals, max_tilt=0.8, max_weight=0.8, turnover_limit=0.1)
    sums = weights.groupby("date")["weight"].sum().to_numpy()
    assert np.allclose(sums, 1.0)
    assert (weights["weight"] >= 0).all()
    assert daily["one_way_turnover"].max() <= 0.1000001
    assert len(daily) == len(prices)


def test_rebalancer_uses_no_same_day_signals():
    dates = [date(2024, 1, d) for d in range(2, 6)]
    prices = pd.DataFrame({"AAA": [100, 100, 100, 100], "BBB": [100, 100, 100, 100]}, index=dates)
    signals = pd.DataFrame([
        {"timestamp": pd.Timestamp("2024-01-02T15:00:00Z"), "ticker": "AAA", "scope": "company", "sentiment": 1.0, "confidence": 1.0, "impact": 8.0, "event_type": "earnings"},
    ])
    weights, _ = backtest_rebalancer(prices, signals, max_tilt=0.8, max_weight=0.8, turnover_limit=0.5)
    day_two = weights[weights["date"] == "2024-01-02"].set_index("ticker")
    assert day_two.loc["AAA", "weight"] == 0.5
    day_three = weights[weights["date"] == "2024-01-03"].set_index("ticker")
    assert day_three.loc["AAA", "weight"] > 0.5


def test_performance_summary_has_both_portfolios():
    daily = pd.DataFrame({"strategy_return": [0.0, 0.01, -0.005], "equal_weight_return": [0.0, 0.005, -0.002], "one_way_turnover": [0.0, 0.1, 0.05]})
    summary = performance_summary(daily)
    assert summary["strategy_cumulative_return"] > summary["equal_weight_cumulative_return"]
    assert np.isclose(summary["total_one_way_turnover"], 0.15)


def test_negative_sentiment_reduces_relative_weight():
    dates = [date(2024, 1, d) for d in range(2, 7)]
    prices = pd.DataFrame({"AAA": [100] * 5, "BBB": [100] * 5}, index=dates)
    signals = pd.DataFrame([
        {"timestamp": pd.Timestamp("2024-01-02T12:00:00Z"), "ticker": "AAA", "scope": "company", "sentiment": -1.0, "confidence": 1.0, "impact": 7.0, "event_type": "earnings"},
    ])
    weights, _ = backtest_rebalancer(prices, signals, max_tilt=0.8, max_weight=0.8, turnover_limit=0.5)
    day_three = weights[weights["date"] == "2024-01-03"].set_index("ticker")
    assert day_three.loc["AAA", "weight"] < 0.5
    assert day_three.loc["BBB", "weight"] > 0.5


def test_spy_benchmark_is_separate_from_index_weights():
    from src.modules.rebalancer.engine import add_spy_benchmark

    dates = pd.Index([date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)])
    daily = pd.DataFrame({
        "date": [d.isoformat() for d in dates],
        "strategy_return": [0.0, 0.01, 0.0],
        "equal_weight_return": [0.0, 0.005, 0.0],
        "one_way_turnover": [0.0, 0.1, 0.0],
    })
    spy = pd.Series([100.0, 102.0, 101.0], index=dates)
    combined = add_spy_benchmark(daily, spy, dates)
    summary = performance_summary(combined)
    assert "spy_return" in combined.columns
    assert "spy_cumulative_return" in summary
    assert np.isclose(summary["spy_cumulative_return"], 0.01)
