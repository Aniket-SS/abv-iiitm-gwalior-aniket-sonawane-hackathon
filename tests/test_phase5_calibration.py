from datetime import date

from src.market.calibration import event_study, load_prices, spearman, summarize_calibration


def test_spearman_positive_and_ties():
    assert spearman([1, 2, 3], [10, 20, 30]) == 1.0
    assert spearman([1, 1, 2], [10, 10, 20]) == 1.0


def test_event_study_abnormal_return_and_market_scope():
    prices = {
        "AAPL": {date(2022, 1, 3): 100, date(2022, 1, 4): 110, date(2022, 1, 5): 121},
        "SPY": {date(2022, 1, 3): 100, date(2022, 1, 4): 105, date(2022, 1, 5): 110},
    }
    signals = [
        {"signal_id": "a", "timestamp": "2022-01-03T12:00:00+00:00", "ticker": "AAPL", "scope": "company", "impact": 8, "confidence": 0.8, "sentiment": 0.5, "event_type": "earnings"},
        {"signal_id": "m", "timestamp": "2022-01-03T12:00:00+00:00", "ticker": "MARKET", "scope": "market", "impact": 9, "confidence": 0.9, "sentiment": -0.5, "event_type": "geopolitical"},
    ]
    rows = event_study(signals, prices, horizons=(1,))
    assert len(rows) == 2
    company = next(row for row in rows if row["ticker"] == "AAPL")
    assert company["forward_return_pct_1d"] == 10.0
    assert company["benchmark_return_pct_1d"] == 4.761905
    assert company["abnormal_return_pct_1d"] == 5.238095
    market = next(row for row in rows if row["ticker"] == "MARKET")
    assert market["abnormal_return_pct_1d"] == 4.761905


def test_event_study_excludes_signals_before_price_history():
    prices = {
        "AAPL": {
            date(2021, 9, 30): 100,
            date(2021, 10, 1): 105,
            date(2021, 10, 4): 110,
        },
        "SPY": {
            date(2021, 9, 30): 100,
            date(2021, 10, 1): 102,
            date(2021, 10, 4): 104,
        },
    }

    signals = [
        {
            "signal_id": "old",
            "timestamp": "2020-03-16T12:00:00+00:00",
            "ticker": "AAPL",
            "scope": "company",
            "impact": 4,
            "confidence": 0.8,
            "sentiment": 0.5,
            "event_type": "other",
        }
    ]

    rows = event_study(signals, prices, horizons=(1,))

    assert rows == []


def test_summary_counts_and_bands():
    rows = [
        {"impact": 2, "abnormal_return_pct_3d": 1.0},
        {"impact": 8, "abnormal_return_pct_3d": -4.0},
        {"impact": 9, "abnormal_return_pct_3d": None},
    ]
    summary = summarize_calibration(rows, horizon=3)
    assert summary["matched_signals"] == 2
    assert summary["bands"][0]["count"] == 1
    assert summary["bands"][2]["count"] == 1


def test_load_stock_yfinance_style_csv(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("Date,Close,Adj Close,Stock Name\n2022-01-03,10,9.5,AAPL\n", encoding="utf-8")
    prices = load_prices(path)
    assert prices["AAPL"][date(2022, 1, 3)] == 9.5
