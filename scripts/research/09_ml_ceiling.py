"""How high can a strict 0.5R win rate go if we let a model pick the trades?

Every hour we open hypothetical long and short brackets (stop = k * prior-day ATR,
target = k/2 * ATR, max 1-15 trading days depending on k, conservative fills) and label
them win/loss. A gradient-boosting classifier is trained walk-forward (expanding window,
2-year test folds, 10-day embargo) on 29 causal features. If a >=90% subset existed and were identifiable
in advance, the top predicted bucket would show it out of sample."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from nqgc import research as R, indicators as ind
from nqgc.engine import TARGET, no_overlap

KS = [0.25, 0.5, 1.0, 2.0]
# max holding scales with bracket size so that time-outs stay rare
HORIZON_DAYS = {0.25: 1, 0.5: 2, 1.0: 5, 2.0: 15}

def build(sym):
    mk = R.load(sym); m, d = mk.m, mk.d
    ts = m.index.asi8; c = m["close"].to_numpy(); o = m["open"].to_numpy()
    mod = m["mod"].to_numpy(); td = m["tday"].to_numpy()
    # decision bars: first bar at/after each :00/:30 mark (bar open exactly on the mark)
    dec = np.flatnonzero((mod % 60 == 0) & ~((mod >= 16*60+15) & (mod < 18*60+30)))
    dec = dec[dec > 300]
    # daily features (prior completed session)
    dc = d["close"]
    D = pd.DataFrame(index=d.index)
    D["atr"] = d["atr14"]; D["atr_ratio"] = d["atr14"] / ind.atr(d, 100)
    for n in (1, 2, 5, 10, 20): D[f"d_ret{n}"] = (dc - dc.shift(n)) / d["atr14"]
    for n in (20, 50, 200): D[f"d_sma{n}"] = (dc - ind.sma(dc, n)) / d["atr14"]
    D["rsi2"] = ind.rsi(dc, 2); D["rsi14"] = ind.rsi(dc, 14); D["ibs"] = ind.ibs(d)
    D["dn"] = ind.down_streak(dc); D["up"] = ind.up_streak(dc)
    D["hi"] = d["high"]; D["lo"] = d["low"]; D["cl"] = dc
    D = D.shift(1)
    Dm = D.reindex(td[dec])
    atr = Dm["atr"].to_numpy()
    X = pd.DataFrame(index=np.arange(len(dec)))
    for mins in (15, 30, 60, 120, 240, 480):
        j = np.searchsorted(ts, ts[dec] - mins * 60_000_000_000) - 1
        j = np.clip(j, 0, None)
        X[f"r{mins}"] = (o[dec] - c[j]) / atr
    # session-so-far features
    first_i = pd.Series(np.arange(len(m)), index=td).groupby(level=0).transform("first").to_numpy()
    hi_so = m["high"].groupby(td).cummax().to_numpy(); lo_so = m["low"].groupby(td).cummin().to_numpy()
    p = dec - 1
    X["r_sess"] = (o[dec] - o[first_i[dec]]) / atr
    X["rng_sess"] = (hi_so[p] - lo_so[p]) / atr
    X["pos_sess"] = (o[dec] - lo_so[p]) / np.maximum(hi_so[p] - lo_so[p], 1e-9)
    X["vs_prev_hi"] = (o[dec] - Dm["hi"].to_numpy()) / atr
    X["vs_prev_lo"] = (o[dec] - Dm["lo"].to_numpy()) / atr
    X["vs_prev_cl"] = (o[dec] - Dm["cl"].to_numpy()) / atr
    j60 = np.searchsorted(ts, ts[dec] - 60 * 60_000_000_000)
    lr = np.diff(np.log(c), prepend=np.log(c[0]))
    cs = np.cumsum(lr ** 2)
    X["rv60"] = np.sqrt(np.maximum(cs[p] - cs[np.clip(j60 - 1, 0, None)], 0)) * o[dec] / atr
    for col in ["atr_ratio", "d_ret1", "d_ret2", "d_ret5", "d_ret10", "d_ret20", "d_sma20", "d_sma50", "d_sma200",
                "rsi2", "rsi14", "ibs", "dn", "up"]:
        X[col] = Dm[col].to_numpy()
    X["mod"] = mod[dec]; X["dow"] = pd.DatetimeIndex(td[dec]).dayofweek
    ok = np.isfinite(atr) & (atr > 0)
    return mk, dec[ok], X[ok].reset_index(drop=True), atr[ok]

def main(sym):
    mk, dec, X, atr = build(sym)
    years = pd.DatetimeIndex(mk.m.index[dec]).year.to_numpy()
    etime = mk.m.index[dec]
    out = []
    for dirn in (1, -1):
        for k in KS:
            tr = R.run(mk, dec, np.full(len(dec), dirn), k * atr, last_idx=dec + HORIZON_DAYS[k] * 1380, overlap=True)
            y = (tr["outcome"].to_numpy() == TARGET).astype(int)
            xit = tr["exit_time"].dt.tz_localize(None).to_numpy()
            pred = np.full(len(y), np.nan)
            for Y in range(2014, years.max() + 1, 2):
                start = np.datetime64(f"{Y}-01-01")
                tr_mask = (xit < start - np.timedelta64(10, "D"))
                te_mask = (years == Y) | (years == Y + 1)
                if te_mask.sum() == 0: continue
                clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=31,
                                                     min_samples_leaf=300, l2_regularization=1.0, early_stopping=False)
                clf.fit(X[tr_mask], y[tr_mask])
                pred[te_mask] = clf.predict_proba(X[te_mask])[:, 1]
            t = tr.assign(p=pred, y=y).dropna(subset=["p"])
            base = t["y"].mean()
            row = dict(sym=sym, dir=dirn, k=k, oos_n=len(t), base_wr=base)
            for thr in (0.7, 0.8, 0.85, 0.9):
                sel = t[t["p"] >= thr]
                row[f"n>={thr}"] = len(sel); row[f"wr>={thr}"] = sel["y"].mean() if len(sel) else np.nan
                if thr in (0.8, 0.85, 0.9) and len(sel):
                    no = no_overlap(sel)
                    row[f"trades>={thr}"] = len(no); row[f"twr>={thr}"] = (no["outcome"] == TARGET).mean()
            # top 1% of predictions regardless of level
            q = t["p"].quantile(0.99); top = t[t["p"] >= q]
            row["top1%_pmin"] = q; row["top1%_wr"] = top["y"].mean()
            out.append(row)
            print({k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in row.items()}, flush=True)
    return pd.DataFrame(out)

if __name__ == "__main__":
    res = pd.concat([main(s) for s in ("NQ", "GC")])
    res.to_csv(str(pathlib.Path(__file__).resolve().parents[2] / "reports" / "research" / "ml_ceiling.csv"), index=False)
