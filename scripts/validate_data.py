"""Validate the HistData proxies against real futures (Yahoo NQ=F / GC=F hourly bars).

Checks: timestamp alignment (best lag per week must be 0), hourly return
correlation, and relative hourly range (proxy vs futures).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nqgc.data import store, yahoo  # noqa: E402


def main() -> None:
    lines = []
    for sym, ysym in (("NQ", "NQ=F"), ("GC", "GC=F")):
        m = store.minutes(sym)
        y = yahoo.fetch(ysym, "1h", "730d")
        h = m[["open", "high", "low", "close"]].resample("1h").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        rf = np.log(y["close"]).diff()
        best = {}
        for lag in (-1, 0, 1):
            hp = h["close"].copy()
            hp.index = hp.index + pd.Timedelta(hours=lag)
            rp = np.log(hp).diff()
            j = pd.concat([rp.rename("p"), rf.rename("f")], axis=1, join="inner").dropna()
            j = j[j["f"].abs() < 0.03]  # drop contract-roll jumps in the futures series
            wk = j.groupby(j.index.tz_localize(None).to_period("W")).apply(lambda t: t["p"].corr(t["f"]) if len(t) > 30 else np.nan)
            best[lag] = wk
            lines.append(f"{sym} lag {lag:+d}h: hourly return corr {j['p'].corr(j['f']):.4f} (n={len(j)})")
        w = pd.concat(best, axis=1).dropna()
        lines.append(f"{sym} weeks compared: {len(w)}; best lag per week: {w.idxmax(axis=1).value_counts().to_dict()}; "
                     f"median weekly corr at lag 0: {w[0].median():.4f}")
        jj = h.join(y[["high", "low", "close"]], rsuffix="_f", how="inner")
        ratio = ((jj["high"] - jj["low"]) / jj["close"]) / ((jj["high_f"] - jj["low_f"]) / jj["close_f"])
        lines.append(f"{sym} median hourly range ratio proxy/futures: {ratio.replace([np.inf], np.nan).median():.3f}")
    print("\n".join(lines))
    out = Path(__file__).resolve().parents[1] / "reports" / "data_validation.txt"
    out.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
