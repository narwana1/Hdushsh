"""Scan daily-signal families (entry next day at 09:30 ET or at the 18:05 ET session open).
Selection uses the in-sample period only (< 2020). OOS columns are stored but not used for ranking."""
import sys, itertools, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import numpy as np, pandas as pd
from nqgc import research as R, indicators as ind
from nqgc.stats import summarize

CUT = "2020-01-01"
rows = []
for sym in ["NQ", "GC"]:
    mk = R.load(sym); d = mk.d.copy()
    c = d["close"]
    feat = pd.DataFrame(index=d.index)
    feat["rsi2"] = ind.rsi(c, 2); feat["rsi3"] = ind.rsi(c, 3)
    feat["ibs"] = ind.ibs(d)
    feat["dn"] = ind.down_streak(c); feat["up"] = ind.up_streak(c)
    mid = ind.sma(c, 20); sd = c.rolling(20).std()
    feat["bbz"] = (c - mid) / sd
    feat["lo5"] = c <= c.rolling(5).min(); feat["hi5"] = c >= c.rolling(5).max()
    feat["sma200"] = c > ind.sma(c, 200); feat["sma50"] = c > ind.sma(c, 50)
    feat["atr"] = d["atr14"]
    F = feat.shift(1)  # signal known at the close of D-1, used on day D
    setups_long = {
        "any": pd.Series(True, index=d.index),
        "rsi2<10": F["rsi2"] < 10, "rsi2<5": F["rsi2"] < 5, "rsi3<20": F["rsi3"] < 20,
        "ibs<0.2": F["ibs"] < 0.2, "dn>=2": F["dn"] >= 2, "dn>=3": F["dn"] >= 3,
        "bbz<-2": F["bbz"] < -2, "bbz<-1.5": F["bbz"] < -1.5, "lo5": F["lo5"] == True,
        "up>=2": F["up"] >= 2, "ibs>0.8": F["ibs"] > 0.8, "hi5": F["hi5"] == True,  # momentum-long variants
    }
    trends = {"none": pd.Series(True, index=d.index), "up200": F["sma200"] == True, "up50": F["sma50"] == True,
              "dn200": F["sma200"] == False, "dn50": F["sma50"] == False}
    ent = {"0930": R.first_bar_at(mk.m, d.index, 570), "1805": R.first_bar_at(mk.m, d.index, 18*60+5, 18*60+60)}
    for (sname, sig), (tname, tr_ok), (ename, e), k, dirn in itertools.product(
            setups_long.items(), trends.items(), ent.items(), [0.5, 1.0, 1.5, 2.0, 3.0], [1, -1]):
        # short side mirrors the long setup (rsi2<10 -> rsi2>90 etc.) by flipping features
        if dirn == -1:
            flip = {"rsi2<10": F["rsi2"] > 90, "rsi2<5": F["rsi2"] > 95, "rsi3<20": F["rsi3"] > 80,
                    "ibs<0.2": F["ibs"] > 0.8, "dn>=2": F["up"] >= 2, "dn>=3": F["up"] >= 3,
                    "bbz<-2": F["bbz"] > 2, "bbz<-1.5": F["bbz"] > 1.5, "lo5": F["hi5"] == True,
                    "up>=2": F["dn"] >= 2, "ibs>0.8": F["ibs"] < 0.2, "hi5": F["lo5"] == True, "any": sig}
            sig_use = flip[sname]
            tflip = {"none": trends["none"], "up200": trends["dn200"], "up50": trends["dn50"],
                     "dn200": trends["up200"], "dn50": trends["up50"]}
            t_use = tflip[tname]
        else:
            sig_use, t_use = sig, tr_ok
        ok = (sig_use & t_use).fillna(False).to_numpy() & (e >= 0) & F["atr"].notna().to_numpy()
        if ok.sum() < 30:
            continue
        tr = R.run(mk, e[ok], np.full(ok.sum(), dirn), (k * F["atr"]).to_numpy()[ok])
        a, b = R.split(tr, CUT)
        sa, sb = summarize(a), summarize(b)
        rows.append(dict(sym=sym, setup=sname, trend=tname, entry=ename, k=k, dir=dirn,
                         is_n=sa.get("trades", 0), is_wr=sa.get("win_rate", np.nan), is_lo=sa.get("wr_ci95_lo", np.nan),
                         is_exp=sa.get("exp_R", np.nan),
                         oos_n=sb.get("trades", 0), oos_wr=sb.get("win_rate", np.nan), oos_exp=sb.get("exp_R", np.nan)))
res = pd.DataFrame(rows)
res.to_csv(str(pathlib.Path(__file__).resolve().parents[2] / "reports" / "research" / "scan_daily.csv"), index=False)
print("variants tested:", len(res))
top = res[res["is_n"] >= 100].sort_values("is_lo", ascending=False)
pd.set_option("display.width", 200)
print(top.head(30)[["sym","setup","trend","entry","k","dir","is_n","is_wr","is_lo","is_exp"]].round(3).to_string())
