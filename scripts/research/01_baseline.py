"""Baseline: enter every day at a fixed time, both directions, 0.5R bracket sized by daily ATR.

Under a driftless random walk the strict win rate is 2/3 regardless of stop size, so this
measures the engine/data against theory and shows how much plain drift adds.
Frictionless fills on purpose (touch = fill, no slippage/commission)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import numpy as np
from nqgc import research as R
from nqgc.engine import Fills, OPEN_AT_END
from nqgc.stats import summarize

for sym in ["NQ", "GC"]:
    mk = R.load(sym)
    atr_prev = mk.d["atr14"].shift(1).to_numpy()  # ATR as of the last completed session
    for mod, label in [(570, "09:30"), (18 * 60 + 5, "18:05")]:
        e = R.first_bar_at(mk.m, mk.d.index, mod)
        ok = (e >= 0) & np.isfinite(atr_prev)
        for k in [0.25, 0.5, 1.0, 2.0]:
            for dirn in [1, -1]:
                tr = R.run(mk, e[ok], np.full(ok.sum(), dirn), k * atr_prev[ok], overlap=True, fills=Fills(0, 0))
                s = summarize(tr)
                print(f"{sym} {label} stop={k:<4}xATR {'long ' if dirn == 1 else 'short'} WR={s['win_rate']*100:5.1f}% "
                      f"n={s['trades']} still-open={int((tr['outcome'] == OPEN_AT_END).sum())}")
