"""Cached, session-annotated minute bars."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import histdata

CACHE = Path(__file__).resolve().parents[3] / "data" / "cache"
PROXY = {"NQ": "NSXUSD", "GC": "XAUUSD"}
NY = "America/New_York"


def minutes(symbol: str, refresh: bool = False) -> pd.DataFrame:
    """1-minute OHLC for the proxy of ``symbol`` ('NQ' or 'GC') with session columns.

    Columns added:
      ny          bar open time in New York
      tday        trading day (Globex convention: bars from 18:00 ET belong to the next day)
      mod         minutes since midnight New York time
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{symbol}_1m.parquet"
    if out.exists() and not refresh:
        return pd.read_parquet(out)
    df = histdata.load_minutes(PROXY[symbol])
    # drop malformed bars
    bad = (df["high"] < df[["open", "close"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1))
    df = df[~bad]
    ny = df.index.tz_convert(NY)
    df["ny"] = ny
    mod = ny.hour * 60 + ny.minute
    df["mod"] = mod.astype(np.int16)
    # Globex day starts at 18:00 ET; shift so evening bars roll into the next date
    df["tday"] = (ny + pd.to_timedelta(np.where(mod >= 18 * 60, 1, 0), unit="D")).normalize().tz_localize(None)
    # weekend bars (Sunday evening session) belong to Monday via the shift above; Saturday should not exist
    df.to_parquet(out)
    return df


def daily_from_minutes(m: pd.DataFrame, start_mod: int | None = None, end_mod: int | None = None) -> pd.DataFrame:
    """Daily bars from minute data, one row per trading day.

    Default: full Globex session (18:00 prev day -> 17:00 ET). With
    ``start_mod``/``end_mod`` (minutes after midnight NY, end exclusive) only that
    window is used, e.g. RTH = (570, 960).

    ``first_i``/``last_i`` are integer positions of the first/last minute bar of
    the window in ``m`` so signals can be mapped back to minute execution.
    """
    pos = np.arange(len(m))
    sel = np.ones(len(m), bool)
    if start_mod is not None:
        mod = m["mod"].to_numpy()
        sel = (mod >= start_mod) & (mod < end_mod)
    mm = m.loc[sel, ["open", "high", "low", "close", "tday"]].assign(i=pos[sel])
    g = mm.groupby("tday")
    return pd.DataFrame(
        {
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "n": g.size(),
            "first_i": g["i"].first(),
            "last_i": g["i"].last(),
        }
    )
