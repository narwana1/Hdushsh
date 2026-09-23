"""Extra out-of-sample check on ^NDX daily bars 2000-01..2010-10 (before the minute data).
Daily resolution: a day touching both stop and target is booked as a loss."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import numpy as np, pandas as pd
from nqgc import indicators as ind
from nqgc.data import yahoo
from nqgc.engine import NQ, simulate, no_overlap
from nqgc.stats import summarize
from nqgc.research import fmt
d = yahoo.fetch("^NDX", "1d")
d.index = d.index.tz_convert("America/New_York").normalize().tz_localize(None).tz_localize("UTC")
d = d[(d.index >= "1999-01-01") & (d.index < "2010-11-15")].copy()
c = d["close"]
F = pd.DataFrame(index=d.index)
F["rsi2"] = ind.rsi(c, 2); F["ibs"] = ind.ibs(d); F["dn"] = ind.down_streak(c)
F["bbz"] = (c - ind.sma(c, 20)) / c.rolling(20).std(); F["up200"] = c > ind.sma(c, 200)
F["atr"] = ind.atr(d, 14)
F = F.shift(1)
conds = np.column_stack([(F["rsi2"] < 10), (F["ibs"] < 0.2), (F["dn"] >= 3), (F["bbz"] < -1.5)]).astype(int)
cnt = conds.sum(1)
atr = F["atr"].to_numpy()
start = np.searchsorted(d.index, pd.Timestamp("2000-01-01", tz="UTC"))
idx = np.arange(len(d))
for name, sig, k in [("C1 dn>=3 k2", conds[:, 2] == 1, 2.0), ("C2 any-of-4 k2", cnt >= 1, 2.0),
                     ("C3 2-of-4 k2", cnt >= 2, 2.0), ("baseline always-long k2", np.ones(len(d), bool), 2.0)]:
    ok = sig & np.isfinite(atr) & (idx >= start)
    tr = no_overlap(simulate(d, idx[ok], np.ones(ok.sum(), int), (k * atr)[ok], NQ))
    s = summarize(tr)
    print(f"{name:26s} {fmt(s)}")
    yr = tr.groupby(tr["entry_time"].dt.year).apply(lambda t: f"{(t['outcome']==1).mean()*100:.0f}%/{len(t)}")
    print("   by year (WR/n):", " ".join(f"{y}:{v}" for y, v in yr.items()))
