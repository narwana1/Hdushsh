"""Glue for research scripts: load data, map daily signals to minute entries, run, summarize."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind
from .data import store
from .engine import GC, NQ, Fills, Instrument, no_overlap, simulate
from .stats import summarize

INSTRUMENTS = {"NQ": NQ, "GC": GC}
RTH = (9 * 60 + 30, 16 * 60)


@dataclass
class Market:
    sym: str
    inst: Instrument
    m: pd.DataFrame  # minute bars
    d: pd.DataFrame  # Globex daily bars (+ indicators)


def load(sym: str) -> Market:
    m = store.minutes(sym)
    d = store.daily_from_minutes(m)
    d = d[d["n"] >= 300]  # drop stub sessions (holiday fragments)
    d["atr14"] = ind.atr(d, 14)
    return Market(sym, INSTRUMENTS[sym], m, d)


def first_bar_at(m: pd.DataFrame, tdays: pd.Index, mod: int, until_mod: int | None = None) -> np.ndarray:
    """Position of the first minute bar on each trading day at/after ``mod`` (NY minutes).

    Returns -1 where no such bar exists before ``until_mod`` (default mod + 30).
    """
    until = mod + 30 if until_mod is None else until_mod
    mods = m["mod"].to_numpy()
    sel = (mods >= mod) & (mods < until)
    pos = np.flatnonzero(sel)
    td = m["tday"].to_numpy()[sel]
    first = pd.Series(pos, index=td).groupby(level=0).first()
    return first.reindex(tdays).fillna(-1).astype(np.int64).to_numpy()


def last_bar_before(m: pd.DataFrame, tdays: pd.Index, mod: int, from_mod: int) -> np.ndarray:
    """Position of the last minute bar on each trading day in [from_mod, mod)."""
    mods = m["mod"].to_numpy()
    sel = (mods >= from_mod) & (mods < mod)
    pos = np.flatnonzero(sel)
    td = m["tday"].to_numpy()[sel]
    last = pd.Series(pos, index=td).groupby(level=0).last()
    return last.reindex(tdays).fillna(-1).astype(np.int64).to_numpy()


def run(mk: Market, entry_idx, direction, stop_dist, rr: float = 0.5, last_idx=None,
        fills: Fills = Fills(), overlap: bool = False) -> pd.DataFrame:
    entry_idx = np.asarray(entry_idx)
    ok = entry_idx >= 0
    if last_idx is not None:
        last_idx = np.asarray(last_idx)[ok]
    tr = simulate(mk.m, entry_idx[ok], np.asarray(direction)[ok], np.asarray(stop_dist, float)[ok],
                  mk.inst, rr=rr, last_idx=last_idx, fills=fills)
    return tr if overlap else no_overlap(tr)


def split(tr: pd.DataFrame, cut: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    t = tr["entry_time"]
    c = pd.Timestamp(cut, tz="UTC")
    return tr[t < c], tr[t >= c]


def fmt(s: dict) -> str:
    if s.get("trades", 0) == 0:
        return "no trades"
    return (f"n={s['trades']:5d} ({s['per_year']:5.1f}/y) WR={s['win_rate']*100:5.1f}% "
            f"[{s['wr_ci95_lo']*100:4.1f},{s['wr_ci95_hi']*100:4.1f}] exp={s['exp_R']:+.3f}R "
            f"PF={s['profit_factor']:.2f} DD={s['max_dd_R']:.1f}R tx={s['time_exits']} amb={s['ambiguous']}")


def report(tr: pd.DataFrame, cut: str = "2020-01-01") -> str:
    a, b = split(tr, cut)
    return f"IS {fmt(summarize(a))} | OOS {fmt(summarize(b))}"
