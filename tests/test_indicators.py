import numpy as np
import pandas as pd
import pytest

from nqgc import indicators as ind


def random_daily(n=400, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = c * np.exp(rng.normal(0, 0.003, n))
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.005, n)))
    lo = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.005, n)))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c},
                        index=pd.date_range("2020-01-01", periods=n, freq="B"))


@pytest.mark.parametrize("fn", [
    lambda d: ind.atr(d, 14),
    lambda d: ind.rsi(d["close"], 2),
    lambda d: ind.sma(d["close"], 20),
    lambda d: ind.ibs(d),
    lambda d: ind.down_streak(d["close"]),
    lambda d: ind.up_streak(d["close"]),
])
def test_indicators_are_causal(fn):
    """Values up to t must not change when later rows are removed or altered."""
    d = random_daily()
    full = fn(d)
    cut = 250
    trunc = fn(d.iloc[:cut])
    pd.testing.assert_series_equal(full.iloc[:cut], trunc, check_names=False)
    d2 = d.copy()
    d2.iloc[cut:] *= 1.5
    pd.testing.assert_series_equal(full.iloc[:cut], fn(d2).iloc[:cut], check_names=False)


def test_down_streak_counts():
    s = pd.Series([10, 9, 8, 7, 8, 7, 7, 6.0])
    assert ind.down_streak(s).tolist() == [0, 1, 2, 3, 0, 1, 0, 1]


def test_rsi_bounds():
    r = ind.rsi(random_daily()["close"], 2).dropna()
    assert ((r >= 0) & (r <= 100)).all()
