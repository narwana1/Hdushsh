"""Scan intraday families: fade/follow the move since the RTH open, prior close (gap) and
position vs prior-day range, at several decision times. Stop = k * prior-day ATR, target = k/2.
Time exit at 15:59 ET (flat by the close) or next-day 15:59. Ranking on IS (< 2020) only."""
import sys, itertools, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import numpy as np, pandas as pd
from nqgc import research as R
from nqgc.stats import summarize

CUT = "2020-01-01"
rows = []
for sym in ["NQ", "GC"]:
    mk = R.load(sym); m, d = mk.m, mk.d
    days = d.index
    atr = d["atr14"].shift(1).to_numpy()
    close_px = m["close"].to_numpy(); open_px = m["open"].to_numpy()
    rth_open_i = R.first_bar_at(m, days, 570, 600)
    prev_close_i = np.r_[-1, R.last_bar_before(m, days, 960, 900)[:-1]]  # prior day's last RTH bar
    eod_i = R.last_bar_before(m, days, 959 + 1, 900)  # last bar before 16:00 -> time exit
    eod_next = np.r_[eod_i[1:], -1]
    hi_prev = d["high"].shift(1).to_numpy(); lo_prev = d["low"].shift(1).to_numpy()
    for T in [575, 600, 630, 690, 780, 870, 930]:
        e = R.first_bar_at(m, days, T, T + 15)
        ok0 = (e >= 0) & (rth_open_i >= 0) & (prev_close_i >= 0) & np.isfinite(atr) & (eod_i > e)
        px = np.where(e >= 0, open_px[np.maximum(e, 0)], np.nan)  # price at decision = entry open
        r_open = (px - open_px[np.maximum(rth_open_i, 0)]) / atr
        r_prev = (px - close_px[np.maximum(prev_close_i, 0)]) / atr
        feats = {"open": r_open, "prev": r_prev}
        for (fname, f), x, mode, k, hold in itertools.product(feats.items(), [0.25, 0.5, 0.75, 1.0, 1.5],
                                                             ["fade", "follow"], [0.1, 0.2, 0.3, 0.5, 1.0], ["eod", "next"]):
            sig = np.where(f > x, 1, np.where(f < -x, -1, 0))
            dirn = -sig if mode == "fade" else sig
            ok = ok0 & (dirn != 0)
            if hold == "next":
                ok &= eod_next > 0
            if ok.sum() < 50:
                continue
            last = (eod_i if hold == "eod" else eod_next)[ok]
            tr = R.run(mk, e[ok], dirn[ok], (k * atr)[ok], last_idx=last)
            a, b = R.split(tr, CUT)
            sa, sb = summarize(a), summarize(b)
            rows.append(dict(sym=sym, T=T, feat=fname, x=x, mode=mode, k=k, hold=hold,
                             is_n=sa.get("trades", 0), is_wr=sa.get("win_rate", np.nan), is_lo=sa.get("wr_ci95_lo", np.nan),
                             is_prof=sa.get("profitable_rate", np.nan), is_exp=sa.get("exp_R", np.nan),
                             oos_n=sb.get("trades", 0), oos_wr=sb.get("win_rate", np.nan), oos_exp=sb.get("exp_R", np.nan)))
        print(sym, T, len(rows), flush=True)
res = pd.DataFrame(rows)
res.to_csv(str(pathlib.Path(__file__).resolve().parents[2] / "reports" / "research" / "scan_intraday.csv"), index=False)
print("variants tested:", len(res))
pd.set_option("display.width", 220)
top = res[res["is_n"] >= 100].sort_values("is_lo", ascending=False)
print(top.head(30)[["sym","T","feat","x","mode","k","hold","is_n","is_wr","is_lo","is_prof","is_exp"]].round(3).to_string())
