#!/usr/bin/env python3
"""Tests for rules.py.

    python backtest/test_rules.py

The regression and mirror tests need the FX Replay bars in backtest/data/<date>/
(not committed; fetch them with fxreplay_fetch.py) and are skipped without them.
"""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxreplay_fetch  # noqa: E402
import rules  # noqa: E402

# Values in the sheet for the two releases that were backtested and independently re-checked.
VERIFIED = {
    "2026-09-11": ("Down", dict(close1="Bottom", close5="Top", close15="Top", high_when="15-60 min",
                                low_when="Not by 16:00", pullback=97, back_open="15-60 min", at_open="Broke through",
                                bias="Bearish", midnight="Above (premium)", liq_wick="Pre-news high/low",
                                liq_main="London high/low", pda="FVG", fvg="Came back & failed (IFVG)", smt="No",
                                setup="A Continuation", r=-1.0)),
    "2026-08-12": ("Down", dict(close1="Middle", close5="Top", close15="Top", high_when="15-60 min",
                                low_when="Not by 16:00", pullback=119, back_open="1-5 min", at_open="Broke through",
                                bias="Bearish", midnight="Above (premium)", liq_wick="Pre-news high/low",
                                liq_main="Pre-news high/low", pda="Breaker", fvg="No FVG", smt="No",
                                setup="None", r=None)),
}
FLIP = {"Top": "Bottom", "Bottom": "Top", "Middle": "Middle", "Bullish": "Bearish", "Bearish": "Bullish",
        "No bias": "No bias", "Above (premium)": "Below (discount)", "Below (discount)": "Above (premium)"}


def data_for(date):
    folder = rules.DATA_DIR / date
    if not all((folder / f).exists() for f in rules.FILES.values()):
        raise unittest.SkipTest(f"no FX Replay data in {folder}")
    return rules.load(dt.date.fromisoformat(date))


class VerifiedRows(unittest.TestCase):
    def test_reproduces_sheet_rows(self):
        for date, (main, want) in VERIFIED.items():
            with self.subTest(date=date):
                res = rules.analyze(dt.date.fromisoformat(date), data_for(date), main)
                self.assertEqual({k: res["values"][k] for k in want}, want)
                self.assertEqual(res["warnings"], [])

    def test_setup_b_on_11_sep(self):
        res = rules.analyze(dt.date(2026, 9, 11), data_for("2026-09-11"), "Down")
        self.assertEqual(res["details"]["B"], {"r_t1": 0.21, "r_t2": 0.31})

    def test_mirrored_day_is_an_up_move(self):
        """Negating every price turns each Down day into an Up day; the Up path must give mirrored answers."""
        for date, (main, _) in VERIFIED.items():
            with self.subTest(date=date):
                data = data_for(date)
                down = rules.analyze(dt.date.fromisoformat(date), data, "Down")["values"]
                res = rules.analyze(dt.date.fromisoformat(date), {k: rules.mirror(v) for k, v in data.items()}, "Up")
                up = res["values"]
                self.assertEqual(res["warnings"], [])
                for k in ("pullback", "back_open", "at_open", "liq_wick", "liq_main", "fvg", "pda", "smt", "setup", "r"):
                    self.assertEqual(up[k], down[k], k)
                for k in ("close1", "close5", "close15", "midnight", "bias"):
                    self.assertEqual(up[k], FLIP[down[k]], k)
                self.assertEqual((up["high_when"], up["low_when"]), (down["low_when"], down["high_when"]))


class Pieces(unittest.TestCase):
    day = rules.Day(dt.date(2026, 9, 11))

    def test_windows(self):
        t = self.day.t
        cases = [(t(8, 30, 14), "0-15 sec"), (t(8, 30, 15), "15-30 sec"), (t(8, 30, 59), "30-60 sec"),
                 (t(8, 34, 59), "1-5 min"), (t(8, 35), "5-15 min"), (t(9, 29, 59), "15-60 min"),
                 (t(9, 30), "9:30-11:00"), (t(15, 59, 59), "11:00-16:00"), (t(16), "Not by 16:00"), (None, "Not by 16:00")]
        for ms, want in cases:
            self.assertEqual(rules.window(self.day, ms), want)

    def test_thirds(self):
        self.assertEqual(rules.third(10, 13, 10)[0], "Bottom")
        self.assertEqual(rules.third(11, 13, 10)[0], "Middle")  # exactly 1/3
        self.assertEqual(rules.third(12, 13, 10)[0], "Top")  # exactly 2/3

    def test_cpi_classes(self):
        self.assertEqual(rules.classify_cpi("0.4", "0.4", "0.3", "0.2"), "Hotter")
        self.assertEqual(rules.classify_cpi("0.1", "0.1", "0.2", "0.2"), "In line")
        self.assertEqual(rules.classify_cpi("0.2", "0.3", "0.2", "0.2"), "Cooler")
        self.assertEqual(rules.classify_cpi("0.3", "0.2", "0.1", "0.2"), "Mixed")

    def test_rounding_is_half_up(self):
        self.assertEqual(rules.half_up(96.5), 97)
        self.assertEqual(rules.half_up(96.49), 96)

    def test_walk_checks_the_stop_first(self):
        bar = [0, 100, 110, 90, 100]
        self.assertEqual(rules.walk([bar], "short", 100, 105, 95), (-1.0, 0))
        self.assertEqual(rules.walk([[0, 100, 104, 95, 96]], "short", 100, 105, 95), (1.0, 0))
        self.assertEqual(rules.walk([[0, 100, 101, 99, 100]], "long", 100, 90, 120), (None, None))

    def test_tuesday_uses_monday_and_friday(self):
        day = rules.Day(dt.date(2026, 7, 14))  # Tuesday
        bars = [[day.t(h, 0, days=dd), 1, 1, 1, 1] for dd, h in ((-5, 18), (-4, 16), (-2, 18), (-1, 16), (-1, 18))]
        prior = rules.prior_sessions(rules.sessions(bars), day)
        self.assertEqual(prior[-2:], [dt.date(2026, 7, 10), dt.date(2026, 7, 13)])

    def test_pd_arrays(self):
        h = 3600 * 1000
        bars = [[0, 10, 11, 9, 10],        # candle 1 of a bullish FVG (high 11)
                [h, 10, 15, 10, 15],
                [2 * h, 15, 16, 12, 16],   # candle 3 (low 12) -> FVG 11-12
                [3 * h, 16, 17, 13, 17]]   # stays above 12 -> still untouched
        fvg = [a for a in rules.pd_arrays(bars, 60, 0, 4 * h) if a["kind"] == "FVG"]
        self.assertEqual([(a["lo"], a["hi"], a["valid"]) for a in fvg], [(11, 12, True)])
        bars[3][3] = 12  # a later low into the gap makes it invalid
        fvg = [a for a in rules.pd_arrays(bars, 60, 0, 4 * h) if a["kind"] == "FVG"]
        self.assertEqual([a["valid"] for a in fvg], [False])
        ob = [[0, 10, 10.5, 8, 9], [h, 9, 12, 9, 11.5], [2 * h, 11.5, 13, 11, 12.5]]  # down candle, then close > 10.5
        found = [(a["lo"], a["hi"], a["valid"]) for a in rules.pd_arrays(ob, 60, 0, 3 * h) if a["kind"] == "Order block"]
        self.assertEqual(found, [(8, 10.5, True)])
        ob.append([3 * h, 12.5, 12.5, 7, 7.5])  # a close below the block's low breaks it
        found = [a["valid"] for a in rules.pd_arrays(ob, 60, 0, 4 * h) if a["kind"] == "Order block"]
        self.assertEqual(found, [False])


class FakeServer(fxreplay_fetch.FXReplay):
    """Serves stored bars like the FX Replay endpoint: `limit` bars up to `to`, the newest one merged."""

    def __init__(self, series):  # noqa: super().__init__ needs a browser page
        self.series = series

    def _request(self, symbol, res, frm, to, limit):
        upto = [list(b) for b in self.series[res] if b[0] <= to][-limit:]
        upto[-1][1:5] = [0, 99999, -99999, 0]
        return list(reversed(upto))


class FetchLogic(unittest.TestCase):
    def test_chunks_rebuild_the_series(self):
        data = data_for("2026-09-11")
        d = dt.date(2026, 9, 11)
        s_end = fxreplay_fetch.ts(d, 10, 1)
        # Trading continues after 10:01:00, so the live server merges that second, not 10:00:59.
        fx = FakeServer({"1": data["nq1m"], "1S": data["nq1s"] + [[s_end, 1, 1, 1, 1, 1, None]], "15": data["nq15"]})
        start, end = fxreplay_fetch.ts(d, 18, days=-10), fxreplay_fetch.ts(d, 17, 5)
        got = fx.bars("NQ", "1", start, end, 12)
        want = [b for b in data["nq1m"] if got[0][0] <= b[0] <= got[-1][0]]
        self.assertEqual(got, want)
        self.assertLessEqual(got[0][0], start)
        stored = [b for b in data["nq1m"] if b[0] <= end]
        self.assertEqual(got[-1][0], stored[-2][0])  # the newest bar of the last request is the merged one
        secs = fx.seconds("NQ", fxreplay_fetch.ts(d, 8, 16), s_end)
        self.assertEqual(secs, [b for b in data["nq1s"] if fxreplay_fetch.ts(d, 8, 16) <= b[0] < s_end])
        got15 = fx.bars("NQ", "15", fxreplay_fetch.ts(d, 18, days=-6), end, 72)
        self.assertEqual(got15, [b for b in data["nq15"] if got15[0][0] <= b[0] <= got15[-1][0]])

    def test_consistency_checks_pass_on_verified_data(self):
        data = data_for("2026-09-11")
        got = {"nq_1m": data["nq1m"], "nq_1s": data["nq1s"], "nq_15": data["nq15"], "nq_60": data["nq60"],
               "nq_240": data["nq240"]}
        self.assertEqual(fxreplay_fetch.check(dt.date(2026, 9, 11), got), [])
        broken = dict(got, nq_1s=[b if i != 500 else [b[0], b[1], b[2] + 50, b[3], b[4]] for i, b in enumerate(got["nq_1s"])])
        self.assertTrue(fxreplay_fetch.check(dt.date(2026, 9, 11), broken))


if __name__ == "__main__":
    unittest.main(verbosity=2)
