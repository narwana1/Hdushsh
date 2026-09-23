"""Yahoo Finance chart API (continuous front-month futures NQ=F / GC=F).

Used for (a) validating the HistData CFD proxies against real futures prices and
(b) long daily history. Not back-adjusted: roll gaps are present.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from .histdata import UA

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "yahoo"


def fetch(symbol: str, interval: str = "1d", rng: str | None = None, cache: bool = True) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{symbol.replace('=', '_').replace('^', '')}_{interval}.parquet"
    if cache and out.exists():
        return pd.read_parquet(out)
    params = {"interval": interval, "includePrePost": "true"}
    if rng:
        params["range"] = rng
    else:
        params.update(period1=0, period2=9_999_999_999)
    r = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params=params, headers={"User-Agent": UA}, timeout=60,
    )
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {k: q[k] for k in ("open", "high", "low", "close", "volume")},
        index=pd.to_datetime(res["timestamp"], unit="s", utc=True),
    ).dropna(subset=["open", "high", "low", "close"])
    df.index.name = "ts_utc"
    df.to_parquet(out)
    return df
