"""Structural check: at 0.5R the only way to push win rate up without prediction is to let
positive drift work over a long holding period (very wide stops). Enter when flat."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import numpy as np, pandas as pd
from nqgc import research as R, indicators as ind
from nqgc.stats import summarize
for sym in ["NQ", "GC"]:
    mk = R.load(sym); d = mk.d
    e = R.first_bar_at(mk.m, d.index, 570)
    atr = d["atr14"].shift(1)
    up200 = (d["close"] > ind.sma(d["close"], 200)).shift(1).fillna(False).astype(bool).to_numpy()
    for filt_name, filt in [("always", np.ones(len(d), bool)), ("up200", up200)]:
        for k in [2, 3, 4, 5, 6, 8, 10]:
            ok = (e >= 0) & atr.notna().to_numpy() & filt
            tr = R.run(mk, e[ok], np.ones(ok.sum(), int), (k * atr).to_numpy()[ok])
            s = summarize(tr)
            hold = (tr["exit_time"] - tr["entry_time"]).dt.days.median()
            a, b = R.split(tr, "2020-01-01")
            sa, sb = summarize(a), summarize(b)
            print(f"{sym} long {filt_name:6s} k={k:<3} n={s['trades']:4d} WR={s['win_rate']*100:5.1f}% "
                  f"(IS {sa.get('win_rate',0)*100:5.1f}% n={sa.get('trades',0)}, OOS {sb.get('win_rate',0)*100:5.1f}% n={sb.get('trades',0)}) "
                  f"exp={s['exp_R']:+.3f}R worst={s['worst_R']:+.2f}R median_hold={hold}d maxDD={s['max_dd_R']:.1f}R")
