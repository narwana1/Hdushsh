"""Trade statistics with honest uncertainty."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as st

from .engine import OPEN_AT_END, STOP, TARGET, TIME

BREAKEVEN_05R = 2.0 / 3.0  # win rate needed at 0.5R before costs


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (mid - half, mid + half)


def max_drawdown(r: np.ndarray) -> float:
    if len(r) == 0:
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(r)])
    return float((np.maximum.accumulate(eq) - eq).max())


def summarize(trades: pd.DataFrame, years: float | None = None) -> dict:
    """Stats over completed trades; a trade still open when the data ends is excluded."""
    n_open = int((trades["outcome"] == OPEN_AT_END).sum()) if len(trades) else 0
    trades = trades[trades["outcome"] != OPEN_AT_END] if n_open else trades
    n = len(trades)
    if n == 0:
        return {"trades": 0, "open_at_end": n_open}
    out = trades["outcome"].to_numpy()
    r = trades["R"].to_numpy()
    wins = int((out == TARGET).sum())
    losses = int((out == STOP).sum())
    timed = int((out == TIME).sum())
    lo, hi = wilson(wins, n)
    gross_win = r[r > 0].sum()
    gross_loss = -r[r < 0].sum()
    if years is None:
        span = (trades["entry_time"].max() - trades["entry_time"].min()).days / 365.25
        years = max(span, 1e-9)
    return {
        "trades": n,
        "per_year": n / years,
        "win_rate": wins / n,  # strict: target filled before stop
        "wr_ci95_lo": lo,
        "wr_ci95_hi": hi,
        "profitable_rate": float((r > 0).mean()),  # incl. time exits in profit
        "stops": losses,
        "time_exits": timed,
        "open_at_end": n_open,
        "ambiguous": int(trades["ambiguous"].sum()),
        "exp_R": float(r.mean()),
        "total_R": float(r.sum()),
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else np.inf,
        "max_dd_R": max_drawdown(r),
        "worst_R": float(r.min()),
        # one-sided p-value that true strict win rate <= breakeven (2/3)
        "p_vs_breakeven": float(st.binomtest(wins, n, BREAKEVEN_05R, alternative="greater").pvalue),
    }


def by_year(trades: pd.DataFrame) -> pd.DataFrame:
    trades = trades[trades["outcome"] != OPEN_AT_END] if len(trades) else trades
    if trades.empty:
        return pd.DataFrame()
    g = trades.groupby(trades["entry_time"].dt.year)
    return pd.DataFrame(
        {
            "trades": g.size(),
            "win_rate": g.apply(lambda t: (t["outcome"] == TARGET).mean()),
            "total_R": g["R"].sum(),
        }
    )
