"""Reproduce every number reported for the final strategy.

Writes reports/strategy_results.md, reports/trades_nq.csv and reports/equity_nq.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nqgc import research as R  # noqa: E402
from nqgc import strategy as S  # noqa: E402
from nqgc.data import store, yahoo  # noqa: E402
from nqgc.engine import NQ, OPEN_AT_END, TARGET, Fills, Instrument  # noqa: E402
from nqgc.stats import by_year, summarize  # noqa: E402

CUT = "2020-01-01"
REPORTS = ROOT / "reports"


def row(label: str, tr: pd.DataFrame) -> str:
    s = summarize(tr)
    if s["trades"] == 0:
        return f"| {label} | 0 | | | | | | |"
    return (f"| {label} | {s['trades']} | {s['per_year']:.1f} | **{s['win_rate']*100:.1f}%** | "
            f"{s['wr_ci95_lo']*100:.1f}-{s['wr_ci95_hi']*100:.1f}% | {s['exp_R']:+.3f} | "
            f"{s['profit_factor']:.2f} | {s['max_dd_R']:.1f} | {s['p_vs_breakeven']:.3f} |")


HEAD = ("| sample | trades | per yr | win rate | 95% CI | exp. R/trade | PF | max DD (R) | p(WR<=66.7%) |\n"
        "|---|---|---|---|---|---|---|---|---|")


def ndx_daily() -> pd.DataFrame:
    d = yahoo.fetch("^NDX", "1d")
    d.index = d.index.tz_convert("America/New_York").normalize().tz_localize(None).tz_localize("UTC")
    return d[(d.index >= "1999-01-01") & (d.index < "2010-11-15")][["open", "high", "low", "close"]]


def main() -> None:
    out: list[str] = []
    nq = R.load("NQ")
    tr = S.backtest(nq)
    is_, oos = R.split(tr, CUT)
    ext = S.backtest_daily(ndx_daily(), NQ, start="2000-01-01")

    out += ["## Headline (NQ, 0.5R, costs included)", "", HEAD,
            row("In-sample 2010-11 .. 2019-12 (used for selection)", is_),
            row("Out-of-sample 2020-01 .. 2026-09", oos),
            row("Extra OOS: ^NDX daily 2000-01 .. 2010-10 (daily bars)", ext),
            row("All minute data 2010-11 .. 2026-09", tr), ""]

    gc = R.load("GC")
    tr_gc = S.backtest(gc)
    out += ["## Same rule on gold (cross-market check, not optimised for GC)", "", HEAD,
            row("GC 2009-2019", R.split(tr_gc, CUT)[0]), row("GC 2020-2026", R.split(tr_gc, CUT)[1]), ""]

    yb = by_year(tr)
    out += ["## NQ by year", "", "| year | trades | win rate | total R |", "|---|---|---|---|"]
    out += [f"| {y} | {int(r.trades)} | {r.win_rate*100:.0f}% | {r.total_R:+.1f} |" for y, r in yb.iterrows()]
    yb2 = by_year(ext)
    out += [f"| {y} (^NDX daily) | {int(r.trades)} | {r.win_rate*100:.0f}% | {r.total_R:+.1f} |" for y, r in yb2.iterrows()]
    out += [""]

    out += ["## Cost / fill sensitivity (NQ, full minute sample)", "", HEAD]
    for label, f, comm in [("frictionless (touch = fill, no slippage, no commission)", Fills(0, 0), 0.0),
                           ("base: 1 tick slip entry+stop, target needs 1-tick trade-through, $5 RT", Fills(1, 1), 5.0),
                           ("harsh: 2 ticks slip, 2-tick trade-through, $10 RT", Fills(2, 2), 10.0)]:
        mk = R.Market("NQ", Instrument("NQ", 0.25, 20.0, comm), nq.m, nq.d)
        out.append(row(label, S.backtest(mk, fills=f)))
    mnq = R.Market("NQ", Instrument("MNQ", 0.25, 2.0, 1.5), nq.m, nq.d)
    out += [row("micro MNQ ($2/pt, $1.50 RT)", S.backtest(mnq)), ""]

    out += ["## What reward:risk would a 90% win rate need? (same entries and 2xATR stop)", "",
            "Random-walk break-even win rate = 1/(1+RR).", "",
            "| RR (target/stop) | break-even WR | IS WR | OOS WR | OOS exp. R/trade |", "|---|---|---|---|---|"]
    for rr in (0.1, 0.2, 0.25, 0.33, 0.5, 0.75, 1.0):
        t = S.backtest(nq, rr=rr)
        a, b = R.split(t, CUT)
        sa, sb = summarize(a), summarize(b)
        out.append(f"| {rr:.2f} | {100/(1+rr):.1f}% | {sa['win_rate']*100:.1f}% | {sb['win_rate']*100:.1f}% | "
                   f"{sb['exp_R']:+.3f} |")
    out += [""]

    out += ["## Robustness (NQ): is 72-73% OOS a fluke of the exact settings?", "",
            "| variant | IS WR (n) | OOS WR (n) | OOS exp. R/trade |", "|---|---|---|---|"]

    def rob(label: str, t: pd.DataFrame) -> str:
        a, b = R.split(t, CUT)
        sa, sb = summarize(a), summarize(b)
        return (f"| {label} | {sa['win_rate']*100:.1f}% ({sa['trades']}) | {sb['win_rate']*100:.1f}% ({sb['trades']}) | "
                f"{sb['exp_R']:+.3f} |")

    m = nq.m
    d16 = store.daily_from_minutes(m[(m["mod"] < 16 * 60) | (m["mod"] >= 18 * 60)]).reindex(nq.d.index)
    out.append(rob("signal close = 16:00 ET instead of 17:00 ET", S.backtest(R.Market("NQ", nq.inst, m, d16))))
    for label, mod in (("entry 18:30 ET", 18 * 60 + 30), ("entry 20:00 ET", 20 * 60), ("entry next day 09:30 ET", 570)):
        out.append(rob(label, S.backtest(nq, S.Params(entry_mod=mod))))
    for n in (2, 3, 4):
        for k in (1.5, 2.0, 2.5):
            tag = " (selected)" if (n, k) == (3, 2.0) else ""
            out.append(rob(f"down closes >= {n}, stop {k} x ATR{tag}", S.backtest(nq, S.Params(min_down_closes=n, stop_atr=k))))
    out += [""]

    done = tr[tr["outcome"] != OPEN_AT_END]
    hold = (done["exit_time"] - done["entry_time"]).dt.total_seconds() / 86400
    out += ["## Trade profile (NQ minute sample)", "",
            f"- median holding time: {hold.median():.1f} days (90th pct {hold.quantile(0.9):.1f} days)",
            f"- worst single trade: {done['R'].min():+.2f}R (includes slippage, commission and any gap through the stop)",
            f"- longest losing streak: {max_streak(done['outcome'].to_numpy() != TARGET)} trades",
            f"- same-minute stop+target (booked as loss): {int(done['ambiguous'].sum())}",
            f"- trades still open when the data ends (excluded from stats): {len(tr) - len(done)}", ""]

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "strategy_results.md").write_text(
        "# Final strategy results (generated by scripts/run_strategy.py)\n\n" + "\n".join(out) + "\n")
    cols = ["entry_time", "exit_time", "entry", "exit", "stop_dist", "outcome", "R"]
    tr[cols].to_csv(REPORTS / "trades_nq.csv", index=False, float_format="%.4f")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(done["exit_time"], done["R"].cumsum(), lw=1.4)
    ax.axvline(pd.Timestamp(CUT, tz="UTC"), color="k", ls="--", lw=1)
    ax.text(pd.Timestamp(CUT, tz="UTC"), ax.get_ylim()[1] * 0.95, "  out-of-sample ->", va="top")
    ax.set_title("NQ 3-down-closes, 0.5R bracket (stop 2xATR, target 1xATR), costs included")
    ax.set_ylabel("cumulative R")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(REPORTS / "equity_nq.png", dpi=120)
    print("\n".join(out))


def max_streak(flags: np.ndarray) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


if __name__ == "__main__":
    main()
