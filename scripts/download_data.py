"""Download all raw data used by the research (idempotent, cached under data/raw)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nqgc.data import histdata, yahoo  # noqa: E402


def main() -> None:
    for pair, first in (("NSXUSD", 2010), ("XAUUSD", 2009)):
        paths = histdata.fetch_all(pair, first, 2025, current_year=2026, current_months=9)
        print(pair, len(paths), "files")
    for sym in ("NQ=F", "GC=F"):
        for interval, rng in (("1d", None), ("1h", "730d")):
            df = yahoo.fetch(sym, interval, rng)
            print(sym, interval, len(df), df.index[0], df.index[-1])


if __name__ == "__main__":
    main()
