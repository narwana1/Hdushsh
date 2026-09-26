import numpy as np
import pandas as pd
import pytest

from nqgc.engine import STOP, TARGET, TIME, OPEN_AT_END, Fills, Instrument, no_overlap, simulate

# tick 1.0, $1/pt, no commission -> easy arithmetic
X = Instrument("X", tick=1.0, point_value=1.0, commission_rt=0.0)
ZERO = Fills(slip_ticks=0, through_ticks=0)


def bars(rows):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], dtype=float)
    df.index = pd.date_range("2024-01-02 14:30", periods=len(df), freq="1min", tz="UTC")
    return df


def one(b, d=1, s=10.0, fills=ZERO, inst=X, last=-1, entry=0, rr=0.5):
    return simulate(b, [entry], [d], [s], inst, rr=rr, last_idx=[last], fills=fills).iloc[0]


def test_long_target_first():
    b = bars([[100, 101, 99, 100], [100, 105, 98, 104], [104, 104, 80, 80]])
    t = one(b)
    assert t.outcome == TARGET and t.exit_idx == 1 and t.exit == 105 and t.R == pytest.approx(0.5)


def test_long_stop_first():
    b = bars([[100, 101, 99, 100], [100, 101, 90, 91], [91, 120, 91, 120]])
    t = one(b)
    assert t.outcome == STOP and t.exit == 90 and t.R == pytest.approx(-1.0)


def test_same_bar_both_levels_is_a_loss():
    b = bars([[100, 101, 99, 100], [100, 106, 89, 100]])
    t = one(b)
    assert t.outcome == STOP and bool(t.ambiguous) and t.R == pytest.approx(-1.0)


def test_entry_bar_is_checked():
    b = bars([[100, 106, 99, 105], [105, 200, 105, 200]])
    t = one(b)
    assert t.outcome == TARGET and t.exit_idx == 0


def test_gap_through_stop_fills_at_open_with_slippage():
    b = bars([[100, 101, 99, 100], [85, 86, 84, 85]])
    t = one(b, fills=Fills(slip_ticks=1, through_ticks=0))
    # entry 101 (1 tick slip), stop 91, gap open 85 -> exit 84
    assert t.entry == 101 and t.outcome == STOP and t.exit == 84
    assert t.R == pytest.approx((84 - 101) / 10)


def test_gap_through_target_only_gets_target_price():
    b = bars([[100, 101, 99, 100], [120, 121, 119, 120]])
    t = one(b)
    assert t.outcome == TARGET and t.exit == 105


def test_target_touch_without_trade_through_does_not_fill():
    b = bars([[100, 105, 99, 100], [100, 100, 89, 89]])
    t = one(b, fills=Fills(slip_ticks=0, through_ticks=1))
    assert t.outcome == STOP


def test_short_mirror():
    b = bars([[100, 101, 99, 100], [100, 102, 95, 96]])
    t = one(b, d=-1)
    assert t.outcome == TARGET and t.exit == 95 and t.R == pytest.approx(0.5)
    b2 = bars([[100, 101, 99, 100], [100, 110, 99, 109]])
    t2 = one(b2, d=-1)
    assert t2.outcome == STOP and t2.exit == 110 and t2.R == pytest.approx(-1.0)


def test_time_exit_at_close_of_last_bar():
    b = bars([[100, 101, 99, 100], [100, 102, 98, 101], [101, 103, 97, 102], [102, 150, 50, 100]])
    t = one(b, last=2)
    assert t.outcome == TIME and t.exit_idx == 2 and t.exit == 102 and t.R == pytest.approx(0.2)


def test_open_at_end_of_data():
    b = bars([[100, 101, 99, 100], [100, 102, 98, 101]])
    assert one(b).outcome == OPEN_AT_END


def test_commission_in_R():
    inst = Instrument("Y", tick=1.0, point_value=10.0, commission_rt=5.0)  # 0.5 pt
    b = bars([[100, 101, 99, 100], [100, 105, 98, 104]])
    t = one(b, inst=inst)
    assert t.R == pytest.approx((5 - 0.5) / 10)


def test_no_overlap():
    b = bars([[100, 101, 99, 100]] + [[100, 101, 99, 100]] * 5 + [[100, 106, 99, 106]])
    tr = simulate(b, [0, 2, 6], [1, 1, 1], [10.0, 10.0, 10.0], X, fills=ZERO)
    kept = no_overlap(tr)
    # first trade occupies bars 0..6, so the second (entry 2) and third (entry 6) are skipped
    assert list(kept["entry_idx"]) == [0]


def test_rejects_bad_input():
    b = bars([[100, 101, 99, 100]])
    with pytest.raises(ValueError):
        simulate(b, [0], [1], [0.0], X)
    with pytest.raises(ValueError):
        simulate(b, [5], [1], [1.0], X)
