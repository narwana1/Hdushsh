"""The strategy that survived selection: NQ three-down-closes mean reversion, 0.5R bracket.

Rules (all times US/Eastern, Globex daily session 18:00 -> 17:00):
  1. After the 17:00 close, if the session closed lower than the previous session's close
     for 3 or more sessions in a row, a long signal is on.
  2. Buy at market at 18:05 when the market reopens.
  3. Stop  = entry - 2.0 x ATR(14)   (Wilder ATR of the Globex daily bars, as of the signal close)
     Target = entry + 1.0 x ATR(14)  -> reward:risk = 0.5
  4. No time exit, no trailing, no scaling. One position at a time; signals that fire while a
     position is open are ignored.

Selected on 2010-11..2019-12 data only (highest Wilson lower bound among 9 pre-registered
candidates); everything later is out-of-sample.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind
from .engine import Fills, no_overlap, simulate
from .research import Market, first_bar_at


@dataclass(frozen=True)
class Params:
    min_down_closes: int = 3
    atr_len: int = 14
    stop_atr: float = 2.0
    rr: float = 0.5
    entry_mod: int = 18 * 60 + 5  # 18:05 ET


def signals(d: pd.DataFrame, p: Params = Params()) -> pd.DataFrame:
    """Per trading day: whether to enter at that day's session open and the stop distance.

    ``d`` is a daily frame indexed by trading day. The row for day D uses only data from
    sessions that closed before D's 18:00 reopen (i.e. rows <= D-1).
    """
    streak = ind.down_streak(d["close"])
    atr = ind.atr(d, p.atr_len)
    out = pd.DataFrame(index=d.index)
    out["long"] = (streak >= p.min_down_closes).shift(1, fill_value=False).astype(bool)
    out["stop_dist"] = (p.stop_atr * atr).shift(1)
    out.loc[out["stop_dist"].isna(), "long"] = False
    return out


def backtest(mk: Market, p: Params = Params(), fills: Fills = Fills(), rr: float | None = None) -> pd.DataFrame:
    """Minute-resolution backtest on a loaded market."""
    sig = signals(mk.d, p)
    e = first_bar_at(mk.m, mk.d.index, p.entry_mod, p.entry_mod + 55)
    ok = sig["long"].to_numpy() & (e >= 0)
    tr = simulate(mk.m, e[ok], np.ones(ok.sum(), np.int64), sig["stop_dist"].to_numpy()[ok], mk.inst,
                  rr=p.rr if rr is None else rr, fills=fills)
    return no_overlap(tr)


def backtest_daily(d: pd.DataFrame, inst, p: Params = Params(), fills: Fills = Fills(),
                   start: str | None = None, rr: float | None = None) -> pd.DataFrame:
    """Daily-bar version (entry at the next day's open) for data without intraday bars.

    A day that touches both stop and target is booked as a loss.
    """
    sig = signals(d, p)
    idx = np.arange(len(d))
    ok = sig["long"].to_numpy()
    if start is not None:
        ok = ok & (d.index >= pd.Timestamp(start, tz=d.index.tz))
    tr = simulate(d, idx[ok], np.ones(ok.sum(), np.int64), sig["stop_dist"].to_numpy()[ok], inst,
                  rr=p.rr if rr is None else rr, fills=fills)
    return no_overlap(tr)
