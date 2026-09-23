"""Mean-reversion setups combined with wide stops (k = 3..8 ATR). IS ranking only."""
import sys, itertools, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import numpy as np, pandas as pd
from nqgc import research as R, indicators as ind
from nqgc.stats import summarize
rows = []
for sym in ["NQ", "GC"]:
    mk = R.load(sym); d = mk.d; c = d["close"]
    F = pd.DataFrame(index=d.index)
    F["rsi2"] = ind.rsi(c, 2); F["ibs"] = ind.ibs(d); F["dn"] = ind.down_streak(c)
    F["bbz"] = (c - ind.sma(c, 20)) / c.rolling(20).std()
    F["up200"] = c > ind.sma(c, 200); F["up50"] = c > ind.sma(c, 50)
    F["dd20"] = (c / c.rolling(20).max() - 1)  # drawdown from 20-day high
    F = F.shift(1)
    atr = d["atr14"].shift(1).to_numpy()
    e = R.first_bar_at(mk.m, d.index, 570)
    setups = {"any": np.ones(len(d), bool), "rsi2<10": (F["rsi2"] < 10).to_numpy(), "rsi2<5": (F["rsi2"] < 5).to_numpy(),
              "ibs<0.2": (F["ibs"] < 0.2).to_numpy(), "dn>=2": (F["dn"] >= 2).to_numpy(), "dn>=3": (F["dn"] >= 3).to_numpy(),
              "bbz<-1.5": (F["bbz"] < -1.5).to_numpy(), "bbz<-2": (F["bbz"] < -2).to_numpy()}
    trends = {"none": np.ones(len(d), bool), "up200": F["up200"].fillna(False).astype(bool).to_numpy(),
              "up50": F["up50"].fillna(False).astype(bool).to_numpy()}
    for (sn, s), (tn, t), k in itertools.product(setups.items(), trends.items(), [3, 4, 5, 6, 8]):
        ok = s & t & (e >= 0) & np.isfinite(atr)
        if ok.sum() < 20: continue
        tr = R.run(mk, e[ok], np.ones(ok.sum(), int), (k * atr)[ok])
        a, b = R.split(tr, "2020-01-01"); sa, sb = summarize(a), summarize(b)
        rows.append(dict(sym=sym, setup=sn, trend=tn, k=k, is_n=sa.get("trades", 0), is_wr=sa.get("win_rate", np.nan),
                         is_lo=sa.get("wr_ci95_lo", np.nan), oos_n=sb.get("trades", 0), oos_wr=sb.get("win_rate", np.nan)))
res = pd.DataFrame(rows); res.to_csv(str(pathlib.Path(__file__).resolve().parents[2] / "reports" / "research" / "scan_swing_wide.csv"), index=False)
print("variants:", len(res))
print(res[res.is_n >= 30].sort_values("is_lo", ascending=False).head(20)[["sym","setup","trend","k","is_n","is_wr","is_lo"]].round(3).to_string())
