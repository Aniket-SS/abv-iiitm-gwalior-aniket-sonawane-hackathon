import numpy as np
import pandas as pd

from scripts.fetch_prices import to_long


def _wide(tickers):
    idx = pd.date_range("2024-01-02", periods=3, freq="B")
    cols = pd.MultiIndex.from_product([tickers, ["Open", "High", "Low", "Close", "Volume"]])
    return pd.DataFrame(np.arange(len(idx) * len(cols), dtype=float).reshape(len(idx), -1),
                        index=idx, columns=cols)


def test_to_long_shape_and_columns():
    out = to_long(_wide(["AAPL", "MSFT"]), ["AAPL", "MSFT"])
    assert list(out.columns) == ["date", "ticker", "open", "high", "low", "close", "volume"]
    assert len(out) == 6
    assert set(out["ticker"]) == {"AAPL", "MSFT"}


def test_missing_ticker_is_skipped():
    out = to_long(_wide(["AAPL", "MSFT"]), ["AAPL", "MSFT", "ZZZZ"])
    assert set(out["ticker"]) == {"AAPL", "MSFT"}
