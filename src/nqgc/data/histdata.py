"""Download and parse HistData.com free 1-minute bars.

Timestamps are the bar *open* time. HistData documents them as fixed EST, but
for these instruments they are in fact New York local time **with** DST: every
week opens Sunday 18:00 NY in both summer and winter. There is one systematic
error: from 2019 onwards the weeks where the US is already on DST but Europe is
not (2nd Sunday of March -> last Sunday of March, last Sunday of October -> 1st
Sunday of November) are stamped one hour early. :func:`to_utc` corrects this.
Verified against Yahoo NQ=F / GC=F hourly bars (2024-05..2026-09): hourly
return correlation 0.96-0.97 overall, 0.99 median per week, best lag 0 in every
week (see scripts/validate_data.py).

Proxies used:
  NSXUSD -> Nasdaq-100 (NQ proxy, trades the same ~23h Globex session)
  XAUUSD -> spot gold  (GC proxy)
"""
from __future__ import annotations

import io
import re
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
BASE = "https://www.histdata.com"
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "histdata"


def _page_url(pair: str, year: int, month: int | None) -> str:
    url = f"{BASE}/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair.lower()}/{year}"
    return url + (f"/{month}" if month else "")


def download(pair: str, year: int, month: int | None = None, session: requests.Session | None = None) -> Path:
    """Download one yearly (or monthly, for the current year) zip. Cached on disk."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{pair.upper()}_{year}" + (f"{month:02d}" if month else "")
    out = RAW_DIR / f"{tag}.zip"
    if out.exists() and out.stat().st_size > 1000:
        return out
    s = session or requests.Session()
    s.headers["User-Agent"] = UA
    page = _page_url(pair, year, month)
    html = s.get(page, timeout=60).text
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" id="\w+" value="([^"]*)"', html))
    if "tk" not in fields:
        raise RuntimeError(f"no download token on {page}")
    r = s.post(f"{BASE}/get.php", data=fields, headers={"Referer": page}, timeout=180)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):
        raise RuntimeError(f"unexpected payload for {tag}: {r.content[:80]!r}")
    out.write_bytes(r.content)
    return out


def parse_zip(path: Path) -> pd.DataFrame:
    """Raw bars indexed by the feed's naive (New York local) timestamps."""
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        raw = z.read(name)
    df = pd.read_csv(
        io.BytesIO(raw), sep=";", header=None,
        names=["ts", "open", "high", "low", "close", "volume"],
        dtype={"ts": str},
    )
    df.index = pd.DatetimeIndex(pd.to_datetime(df["ts"], format="%Y%m%d %H%M%S"), name="ts_raw")
    return df[["open", "high", "low", "close"]].astype(np.float64)


def _us_eu_dst_gap_sundays(years) -> set:
    """Sundays starting weeks in which the US is on DST and the EU is not."""
    out = set()
    for y in years:
        mar = [d for d in pd.date_range(f"{y}-03-01", f"{y}-03-31") if d.dayofweek == 6]
        d, end = mar[1], mar[-1]
        while d < end:
            out.add(d.date())
            d += pd.Timedelta(days=7)
        eu_end = [d for d in pd.date_range(f"{y}-10-01", f"{y}-10-31") if d.dayofweek == 6][-1]
        us_end = [d for d in pd.date_range(f"{y}-11-01", f"{y}-11-30") if d.dayofweek == 6][0]
        d = eu_end
        while d < us_end:
            out.add(d.date())
            d += pd.Timedelta(days=7)
    return out


def to_utc(raw: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Convert (sorted) feed timestamps to UTC, fixing the 2019+ US/EU DST-gap weeks."""
    if not raw.is_monotonic_increasing:
        raise ValueError("timestamps must be sorted: weeks are detected from weekend gaps")
    r = pd.Series(raw)
    week = (r.diff() > pd.Timedelta(hours=20)).cumsum().to_numpy()  # weekend gaps split weeks
    first = r.groupby(week).first()
    sunday = (first - pd.to_timedelta((first.dt.dayofweek + 1) % 7, unit="D")).dt.date
    gap = _us_eu_dst_gap_sundays(range(raw.min().year, raw.max().year + 1))
    shift_w = np.array([1 if (s in gap and f.year >= 2019) else 0 for s, f in zip(sunday, first)])
    local = raw + pd.to_timedelta(shift_w[week], unit="h")
    # DST switches happen on Sunday 02:00 while the market is closed, so no ambiguous times
    return pd.DatetimeIndex(local).tz_localize("America/New_York").tz_convert("UTC").rename("ts_utc")


def fetch_all(pair: str, first_year: int, last_full_year: int, current_year: int | None = None,
              current_months: int = 0, pause: float = 1.5) -> list[Path]:
    s = requests.Session()
    paths = []
    for y in range(first_year, last_full_year + 1):
        paths.append(download(pair, y, session=s))
        time.sleep(pause)
    if current_year:
        for m in range(1, current_months + 1):
            try:
                paths.append(download(pair, current_year, m, session=s))
            except Exception as e:  # current month may not be published yet
                print(f"skip {pair} {current_year}-{m:02d}: {e}")
            time.sleep(pause)
    return paths


def load_minutes(pair: str) -> pd.DataFrame:
    """All cached zips for a pair, concatenated, de-duplicated, sorted (UTC index)."""
    files = sorted(RAW_DIR.glob(f"{pair.upper()}_*.zip"))
    if not files:
        raise FileNotFoundError(f"no HistData files for {pair}; run scripts/download_data.py")
    df = pd.concat([parse_zip(f) for f in files])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index = to_utc(df.index)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df
