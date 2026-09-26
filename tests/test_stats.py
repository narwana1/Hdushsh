import numpy as np
import pandas as pd
import pytest

from nqgc.engine import OPEN_AT_END, STOP, TARGET
from nqgc.stats import summarize, wilson


def trades(outcomes, rs):
    n = len(outcomes)
    return pd.DataFrame({
        "entry_time": pd.date_range("2020-01-01", periods=n, freq="30D", tz="UTC"),
        "outcome": outcomes, "R": rs, "ambiguous": [False] * n,
    })


def test_summary_counts_and_excludes_open_trade():
    s = summarize(trades([TARGET, TARGET, STOP, OPEN_AT_END], [0.5, 0.5, -1.0, -0.3]))
    assert s["trades"] == 3 and s["open_at_end"] == 1
    assert s["win_rate"] == pytest.approx(2 / 3)
    assert s["exp_R"] == pytest.approx(0.0)
    assert s["max_dd_R"] == pytest.approx(1.0)


def test_wilson_interval():
    lo, hi = wilson(90, 100)
    assert lo == pytest.approx(0.8256, abs=1e-3) and hi == pytest.approx(0.9448, abs=1e-3)
    assert np.isnan(wilson(0, 0)[0])
