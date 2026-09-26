import numpy as np
import pandas as pd

from nqgc import strategy as S
from nqgc.engine import Instrument, TARGET


def daily(closes):
    c = np.asarray(closes, float)
    return pd.DataFrame({"open": c, "high": c + 1.0, "low": c - 1.0, "close": c},
                        index=pd.date_range("2024-01-01", periods=len(c), freq="B", tz="UTC"))


def test_signal_fires_the_day_after_the_third_lower_close():
    closes = [100 + i for i in range(20)] + [118, 117, 116, 117, 118]  # 3 lower closes at rows 20-22
    sig = S.signals(daily(closes))
    fired = list(np.flatnonzero(sig["long"].to_numpy()))
    assert fired == [23]  # third lower close is row 22, entry on row 23


def test_signal_for_day_d_ignores_day_d_data():
    closes = [100 + i for i in range(20)] + [118, 117, 116, 117, 118, 119]
    d = daily(closes)
    base = S.signals(d)
    d2 = d.copy()
    d2.iloc[23, :] = [50.0, 51.0, 49.0, 50.0]  # crash on the entry day itself
    alt = S.signals(d2)
    pd.testing.assert_series_equal(base["long"].iloc[:24], alt["long"].iloc[:24])
    pd.testing.assert_series_equal(base["stop_dist"].iloc[:24], alt["stop_dist"].iloc[:24])


def test_bracket_is_half_R():
    closes = [100 + i for i in range(20)] + [118, 117, 116] + [117] * 3 + [200]
    d = daily(closes)
    inst = Instrument("X", 0.25, 1.0, 0.0)
    from nqgc.engine import Fills
    tr = S.backtest_daily(d, inst, fills=Fills(0, 0))
    assert len(tr) == 1
    t = tr.iloc[0]
    assert t.outcome == TARGET
    assert np.isclose(t.exit - t.entry, 0.5 * t.stop_dist)
