"""Aggregate the rule scans: how many variants, how high did in-sample win rates go, and what
happened to the in-sample leaders out of sample (2020-2026)."""
import sys, pathlib
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[2] / "reports" / "research"
scans = {"daily signals (02)": ("scan_daily.csv", 100), "intraday (03)": ("scan_intraday.csv", 100),
         "mean-reversion + wide stops (05)": ("scan_swing_wide.csv", 30)}
total = 0
print("| scan | variants | min IS trades | best IS WR | top-10 by IS: mean IS WR -> mean OOS WR | "
      "variants with IS WR >= 90% | ... of those with OOS WR >= 90% (OOS n>=20) |")
print("|---|---|---|---|---|---|---|")
for name, (f, nmin) in scans.items():
    r = pd.read_csv(OUT / f)
    total += len(r)
    q = r[r["is_n"] >= nmin].sort_values("is_lo", ascending=False)
    top = q.head(10)
    hi = r[(r["is_n"] >= 30) & (r["is_wr"] >= 0.9)]
    hi_ok = hi[(hi["oos_n"] >= 20) & (hi["oos_wr"] >= 0.9)]
    print(f"| {name} | {len(r)} | {nmin} | {q['is_wr'].max()*100:.1f}% | "
          f"{top['is_wr'].mean()*100:.1f}% -> {top['oos_wr'].mean()*100:.1f}% | {len(hi)} | {len(hi_ok)} |")
print(f"\nrule variants in scans 02/03/05: {total} (+28 wide-stop, 9 candidates, 12 popular-claim configs)")

ml = OUT / "ml_ceiling.csv"
if ml.exists():
    m = pd.read_csv(ml)
    print("\nWalk-forward model (09), out-of-sample 2014-2026. Realised strict win rate of the trades the model")
    print("was most confident about (non-overlapping trades taken whenever predicted P(win) >= 0.9):\n")
    print("| market | side | stop (x ATR) | base WR (all hours) | trades with P>=0.9 | their WR | WR of top-1% hourly predictions (overlapping) |")
    print("|---|---|---|---|---|---|---|")
    for _, r in m.iterrows():
        n9 = int(r.get("trades>=0.9", 0) or 0)
        wr9 = f"{r['twr>=0.9']*100:.1f}%" if n9 else "-"
        print(f"| {r['sym']} | {'long' if r['dir'] == 1 else 'short'} | {r['k']} | {r['base_wr']*100:.1f}% | {n9} | {wr9} | "
              f"{r['top1%_wr']*100:.1f}% |")
