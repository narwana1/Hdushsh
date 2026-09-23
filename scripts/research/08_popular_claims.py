"""Check two setups often advertised as ~90% win rate, forced into a strict 0.5R bracket.
1) RTH gap fill: at the 09:30 open fade the gap; target = prior 16:00 close (|gap| away),
   stop = 2*|gap| beyond entry, flat at 15:59.
2) Opening-range breakout (15 min): first break of the OR high/low, enter next bar open,
   stop at the opposite side of the range, target = 0.5 * stop distance, flat at 15:59."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import numpy as np, pandas as pd
from nqgc import research as R
from nqgc.stats import summarize
for sym, or_start in [("NQ", 570), ("GC", 500)]:
    mk = R.load(sym); m, d = mk.m, mk.d
    days = d.index; atr = d["atr14"].shift(1).to_numpy()
    o, h, l, c = (m[k].to_numpy() for k in ("open", "high", "low", "close"))
    mods = m["mod"].to_numpy(); tdn = m["tday"].to_numpy()
    e930 = R.first_bar_at(m, days, 570, 575)
    prev_close_i = np.r_[-1, R.last_bar_before(m, days, 960, 900)[:-1]]
    eod = R.last_bar_before(m, days, 960, 900)
    ok = (e930 >= 0) & (prev_close_i >= 0) & (eod > e930) & np.isfinite(atr)
    gap = np.where(ok, o[np.maximum(e930, 0)] - c[np.maximum(prev_close_i, 0)], np.nan)
    g_atr = np.abs(gap) / atr
    print(f"== {sym} gap fill (0.5R: target = prior close, stop = 2x gap)")
    for lo_, hi_ in [(0.02, 0.1), (0.1, 0.2), (0.2, 0.35), (0.35, 0.6), (0.6, 1.5)]:
        sel = ok & (g_atr >= lo_) & (g_atr < hi_) & (np.abs(gap) >= 4 * mk.inst.tick)
        tr = R.run(mk, e930[sel], -np.sign(gap[sel]).astype(int), 2 * np.abs(gap[sel]), last_idx=eod[sel])
        s = summarize(tr)
        print(f"  |gap| {lo_:.2f}-{hi_:.2f} ATR: {R.fmt(s)}  profitable={s['profitable_rate']*100:.1f}%")
    # opening range breakout
    ors, ore = or_start, or_start + 15
    rows_e, rows_d, rows_s, rows_x = [], [], [], []
    starts = R.first_bar_at(m, days, ors, ore); ends = R.last_bar_before(m, days, ore, ors)
    for n in range(len(days)):
        a, b = starts[n], ends[n]
        if a < 0 or b < a or eod[n] <= b or not np.isfinite(atr[n]): continue
        hi_, lo_ = h[a:b+1].max(), l[a:b+1].min()
        j = b + 1
        seg_h, seg_l = h[j:eod[n]], l[j:eod[n]]
        up = np.flatnonzero(seg_h > hi_); dn = np.flatnonzero(seg_l < lo_)
        fu = up[0] if len(up) else 10**9; fd = dn[0] if len(dn) else 10**9
        if min(fu, fd) >= 10**9 or fu == fd: continue
        k = j + min(fu, fd) + 1  # enter at next bar open
        if k >= eod[n]: continue
        dirn = 1 if fu < fd else -1
        stop_level = lo_ if dirn == 1 else hi_
        dist = (o[k] - stop_level) * dirn
        if dist <= 2 * mk.inst.tick: continue
        rows_e.append(k); rows_d.append(dirn); rows_s.append(dist); rows_x.append(eod[n])
    tr = R.run(mk, np.array(rows_e), np.array(rows_d), np.array(rows_s), last_idx=np.array(rows_x))
    s = summarize(tr)
    print(f"== {sym} 15-min ORB, stop = other side of range, target = 0.5 * stop: {R.fmt(s)} profitable={s['profitable_rate']*100:.1f}%")
