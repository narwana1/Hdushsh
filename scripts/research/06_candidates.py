"""Pre-registered candidate set built from the IS scan leaders (NQ long mean reversion).
Selection by IS Wilson lower bound; OOS printed separately afterwards."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import numpy as np, pandas as pd
from nqgc import research as R, indicators as ind
from nqgc.stats import summarize
mk = R.load("NQ"); d = mk.d; c = d["close"]
F = pd.DataFrame(index=d.index)
F["rsi2"] = ind.rsi(c, 2); F["ibs"] = ind.ibs(d); F["dn"] = ind.down_streak(c)
F["bbz"] = (c - ind.sma(c, 20)) / c.rolling(20).std(); F["up200"] = c > ind.sma(c, 200)
F = F.shift(1)
conds = np.column_stack([(F["rsi2"] < 10), (F["ibs"] < 0.2), (F["dn"] >= 3), (F["bbz"] < -1.5)]).astype(int)
cnt = conds.sum(1)
up200 = F["up200"].fillna(False).astype(bool).to_numpy()
atr = d["atr14"].shift(1).to_numpy()
e18 = R.first_bar_at(mk.m, d.index, 18*60+5, 19*60)
e93 = R.first_bar_at(mk.m, d.index, 570)
cands = {
    "C1 dn>=3 k2 18:05": (conds[:, 2] == 1, 2.0, e18),
    "C2 any-of-4 k2 18:05": (cnt >= 1, 2.0, e18),
    "C3 2-of-4 k2 18:05": (cnt >= 2, 2.0, e18),
    "C4 any-of-4 k1.5 18:05": (cnt >= 1, 1.5, e18),
    "C5 2-of-4 k1.5 18:05": (cnt >= 2, 1.5, e18),
    "C6 any-of-4 up200 k2 18:05": ((cnt >= 1) & up200, 2.0, e18),
    "C7 2-of-4 up200 k2 18:05": ((cnt >= 2) & up200, 2.0, e18),
    "C8 2-of-4 k2 09:30": (cnt >= 2, 2.0, e93),
    "C9 3-of-4 k2 18:05": (cnt >= 3, 2.0, e18),
}
out = {}
for name, (sig, k, e) in cands.items():
    ok = sig & (e >= 0) & np.isfinite(atr)
    tr = R.run(mk, e[ok], np.ones(ok.sum(), int), (k * atr)[ok])
    a, b = R.split(tr, "2020-01-01")
    out[name] = (tr, summarize(a), summarize(b))
    print(f"{name:28s} IS: {R.fmt(summarize(a))}")
best = max(out, key=lambda n: out[n][1]["wr_ci95_lo"])
print("\nIS-selected:", best)
print("\nOOS (for all, to show selection was not OOS-driven):")
for name, (tr, sa, sb) in out.items():
    print(f"{name:28s} OOS: {R.fmt(sb)}")
