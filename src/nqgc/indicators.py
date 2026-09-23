"""Causal indicators: the value on row t uses rows <= t only."""
from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(d: pd.DataFrame) -> pd.Series:
    pc = d["close"].shift(1)
    return pd.concat([d["high"] - d["low"], (d["high"] - pc).abs(), (d["low"] - pc).abs()], axis=1).max(axis=1)


def atr(d: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(d).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def rsi(s: pd.Series, n: int = 2) -> pd.Series:
    diff = s.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(up.notna())


def ibs(d: pd.DataFrame) -> pd.Series:
    """Internal bar strength: where the close sits in the day's range (0 = low, 1 = high)."""
    rng = (d["high"] - d["low"]).replace(0, np.nan)
    return (d["close"] - d["low"]) / rng


def down_streak(s: pd.Series) -> pd.Series:
    """Number of consecutive lower closes ending at t."""
    dn = (s.diff() < 0).astype(int).to_numpy()
    out = np.zeros(len(dn), int)
    for i in range(1, len(dn)):
        out[i] = out[i - 1] + 1 if dn[i] else 0
    return pd.Series(out, index=s.index)


def up_streak(s: pd.Series) -> pd.Series:
    return down_streak(-s)
