#!/usr/bin/env python3
"""Compute the new CPI Log columns for one CPI release from FX Replay bars.

The rules are written out in backtest/RULES.md. test_rules.py checks that this
file still reproduces the two verified sheet rows (12 Aug 2026 and 11 Sep 2026).

    python backtest/rules.py --date 2026-09-11 --main Down --cpi Hotter
    python backtest/rules.py --date 2026-07-14 --main Up --cpi-numbers 0.3 0.2 0.2 0.3

Reads backtest/data/<date>/*.json (written by fxreplay_fetch.py) and writes
backtest/out/<date>.json, which sheet.py can fill into the sheet.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_template as bt  # noqa: E402

NY = ZoneInfo("America/New_York")
TICK = 0.25
DATA_DIR = ROOT / "backtest" / "data"
OUT_DIR = ROOT / "backtest" / "out"
FILES = {"nq1m": "nq_1m.json", "nq1s": "nq_1s.json", "es1m": "es_1m.json",
         "nq15": "nq_15.json", "nq60": "nq_60.json", "nq240": "nq_240.json"}
LIQ_ORDER = bt.LIQ[1:]  # smallest -> biggest
KEY_LEVELS = ("London high/low", "Prev day high/low", "Prev week high/low")  # Setup B context
WINDOW_ENDS = [(8, 30, 15), (8, 30, 30), (8, 31, 0), (8, 35, 0), (8, 45, 0), (9, 30, 0), (11, 0, 0), (16, 0, 0)]
OPTIONS = {c.key: c.options for c in bt.COLUMNS if c.options}


# ------------------------------------------------------------------ bar helpers (bar = [t_ms, o, h, l, c, ...])
def hi(bs):
    return max(b[2] for b in bs)


def lo(bs):
    return min(b[3] for b in bs)


def first(bs, pred):
    return next((b for b in bs if pred(b)), None)


def mirror(bars):
    """Negate prices (high and low swap) so an Up move can reuse the Down rules."""
    return [[b[0], -b[1], -b[3], -b[2], -b[4], *b[5:]] for b in bars]


def fmt(x):
    s = repr(float(x))
    return s[:-2] if s.endswith(".0") else s


def ny(ms, f="%H:%M:%S"):
    return dt.datetime.fromtimestamp(ms / 1000, NY).strftime(f)


def half_up(x):
    return int(Decimal(repr(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class Day:
    """Millisecond timestamps in New York time around the release date."""

    def __init__(self, date: dt.date):
        self.date = date

    def t(self, h, mi=0, s=0, days=0):
        d = self.date + dt.timedelta(days=days)
        return int(dt.datetime(d.year, d.month, d.day, h, mi, s, tzinfo=NY).timestamp() * 1000)


class Series:
    """1-second bars where available (release morning), 1-minute bars elsewhere."""

    def __init__(self, m1, s1):
        self.m1, self.s1 = m1, s1
        self.by_t = {b[0]: b for b in m1}
        self.s1_start = s1[0][0] // 60000 * 60000
        self.s1_end = (s1[-1][0] // 60000 + 1) * 60000

    def stream(self, start, end):
        return ([b for b in self.m1 if start <= b[0] < min(end, self.s1_start)]
                + [b for b in self.s1 if max(start, self.s1_start) <= b[0] < min(end, self.s1_end)]
                + [b for b in self.m1 if max(start, self.s1_end) <= b[0] < end])


def window(day, ms):
    if ms is None:
        return bt.NEVER
    for end, name in zip(WINDOW_ENDS, bt.WIN_OPEN):
        if ms < day.t(*end):
            return name
    return bt.NEVER


def third(close, h, l):
    pos = (close - l) / (h - l)
    return ("Bottom" if pos < 1 / 3 else "Middle" if pos < 2 / 3 else "Top"), pos


def trading_date(ms):
    """CME session date: bars from 18:00 belong to the next day."""
    return (dt.datetime.fromtimestamp(ms / 1000, NY) + dt.timedelta(hours=6)).date()


def sessions(m1):
    out = {}
    for b in m1:
        out.setdefault(trading_date(b[0]), []).append(b)
    return out


def prior_sessions(sess, day):
    prior = sorted(d for d in sess if d < day.date)
    if len(prior) < 2:
        raise ValueError("1m data must cover the two sessions before the release")
    return prior


def levels(m1, day, sess, side):
    """Reference highs or lows with their value and whether they were still untouched at 8:30."""
    prior = prior_sessions(sess, day)
    monday = day.date - dt.timedelta(days=day.date.weekday())
    week = [d for d in prior if monday - dt.timedelta(days=7) <= d < monday]
    spans = {
        "Pre-news high/low": [b for b in m1 if day.t(7) <= b[0] < day.t(8, 30)],
        "Asia high/low": [b for b in m1 if day.t(20, days=-1) <= b[0] < day.t(0)],
        "London high/low": [b for b in m1 if day.t(2) <= b[0] < day.t(5)],
        "Prev day high/low": sess[prior[-1]],
        "Prev week high/low": [b for d in week for b in sess[d]],
    }
    out = {}
    for name, bs in spans.items():
        if not bs:
            raise ValueError(f"no bars for {name} - fetch more 1m history")
        val = hi(bs) if side == "high" else lo(bs)
        beyond = (lambda b: b[2] > val) if side == "high" else (lambda b: b[3] < val)
        taken = first([b for b in m1 if bs[-1][0] + 60000 <= b[0] < day.t(8, 30)], beyond)
        out[name] = {"value": val, "intact": taken is None, "taken_at": taken[0] if taken else None}
    return out


def biggest(lv, test):
    taken = [n for n in LIQ_ORDER if lv[n]["intact"] and test(lv[n]["value"])]
    return taken[-1] if taken else "None"


def daily_bias(sess, day):
    prior = prior_sessions(sess, day)
    d2, d1 = sess[prior[-2]], sess[prior[-1]]
    h2, l2 = hi(d2), lo(d2)
    h1, l1, c1 = hi(d1), lo(d1), d1[-1][4]
    facts = (f"D-1 ({prior[-1]:%d %b}) H {fmt(h1)} L {fmt(l1)} C {fmt(c1)} vs "
             f"D-2 ({prior[-2]:%d %b}) H {fmt(h2)} L {fmt(l2)}")
    if c1 > h2:
        return "Bullish", facts + " -> closed above the D-2 high"
    if c1 < l2:
        return "Bearish", facts + " -> closed below the D-2 low"
    if h1 > h2 and not l1 < l2:
        return "Bearish", facts + " -> traded above the D-2 high but closed inside"
    if l1 < l2 and not h1 > h2:
        return "Bullish", facts + " -> traded below the D-2 low but closed inside"
    return "No bias", facts + " -> inside day, or outside day that closed inside"


def pd_arrays(bars, minutes, since, cutoff):
    """Bullish FVGs, order blocks and breakers whose first candle opened at/after `since`, all closed by `cutoff`."""
    closed = [b for b in bars if b[0] + minutes * 60000 <= cutoff]
    found = []
    for i in range(len(closed) - 2):
        a, c = closed[i], closed[i + 2]
        if a[0] >= since and a[2] < c[3]:
            top = c[3]
            touched = first(closed[i + 3:], lambda x: x[3] <= top)
            found.append({"kind": "FVG", "t": a[0], "lo": a[2], "hi": top, "valid": touched is None})
    for i in range(len(closed) - 1):
        ob, nxt = closed[i], closed[i + 1]
        if ob[0] < since:
            continue
        if ob[4] < ob[1] and nxt[4] > nxt[1]:  # last down-close candle before an up move
            j = next((k for k in range(i + 1, min(i + 4, len(closed))) if closed[k][4] > ob[2]), None)
            if j is not None:
                broken = first(closed[j + 1:], lambda x: x[4] < ob[3])
                found.append({"kind": "Order block", "t": ob[0], "lo": ob[3], "hi": ob[2], "valid": broken is None})
        if ob[4] > ob[1] and nxt[4] < nxt[1]:  # bearish order block that later flips into a bullish breaker
            j = next((k for k in range(i + 1, min(i + 4, len(closed))) if closed[k][4] < ob[3]), None)
            if j is not None:
                f = next((k for k in range(j + 1, len(closed)) if closed[k][4] > ob[2]), None)
                if f is not None:
                    fail = first(closed[f + 1:], lambda x: x[4] < ob[3])
                    found.append({"kind": "Breaker", "t": ob[0], "lo": ob[3], "hi": ob[2], "valid": fail is None})
    return found


def walk(bars, side, entry, stop, target):
    """(R, time): -1 when the stop is hit first (checked first inside a bar), reward/risk when the target is."""
    risk = abs(entry - stop)
    for b in bars:
        if (b[2] >= stop) if side == "short" else (b[3] <= stop):
            return -1.0, b[0]
        if (b[3] <= target) if side == "short" else (b[2] >= target):
            return round(abs(target - entry) / risk, 2), b[0]
    return None, None


def classify_cpi(cpi, cpi_fc, core, core_fc):
    signs = {(Decimal(a) > Decimal(f)) - (Decimal(a) < Decimal(f)) for a, f in ((cpi, cpi_fc), (core, core_fc))}
    if {1, -1} <= signs:
        return "Mixed"
    return "Hotter" if 1 in signs else "Cooler" if -1 in signs else "In line"


# ------------------------------------------------------------------ direction-dependent columns
def analyze_down(day, d, sign):
    """Columns that depend on the main move, written for a Down move. Up moves arrive mirrored (sign = -1)."""
    P = lambda x: fmt(sign * x)  # noqa: E731
    W = {"wick": "high", "main": "low", "above": "above", "below": "below"} if sign == 1 else \
        {"wick": "low", "main": "high", "above": "below", "below": "above"}
    nq = Series(d["nq1m"], d["nq1s"])
    m1 = nq.by_t
    O, H1, L1 = m1[day.t(8, 30)][1:4]
    if not O > L1:
        raise ValueError("main move never went past the 8:30 open")
    end = day.t(16)
    out, rep, notes, warn, det = {}, [], [], [], {}
    sec = [b for b in d["nq1s"] if day.t(8, 30) <= b[0] < day.t(8, 31)]
    t_low = min(b[0] for b in sec if b[3] == L1)
    start = max(b[0] for b in sec if b[0] <= t_low and b[2] >= O)
    wick_ext = hi([b for b in sec if b[0] <= start])
    main_ext = lo([m1[day.t(8, 30 + i)] for i in range(15)])
    rep.append(f"Main move starts {ny(start)} (last second {W['above']} the open before the 1-min {W['main']}); "
               f"wick {W['wick']} {P(wick_ext)}; main-move {W['main']} by 8:45 {P(main_ext)}")

    # Deepest pullback
    brk = first(nq.stream(day.t(8, 31), day.t(8, 45)), lambda b: b[3] < L1)
    pb_bars = nq.stream(day.t(8, 31), brk[0] if brk else day.t(8, 45))
    if pb_bars:
        pb = hi(pb_bars)
        pct = (pb - L1) / (O - L1) * 100
        pb_t = min(b[0] for b in pb_bars if b[2] == pb)
        rep.append(f"Pullback: extreme {P(pb)} at {ny(pb_t)} (window 8:31 -> {ny(brk[0]) if brk else '8:45'}) -> "
                   f"({P(pb)} - {P(L1)}) / ({P(O)} - {P(L1)}) = {pct:.2f}%")
    else:
        pct = 0.0
        rep.append("Pullback: the 1-min extreme broke at 8:31:00 -> 0%")
    out["pullback"] = half_up(pct)

    # Back to the 8:30 open, and what price did there
    back = first(nq.stream(start + 1000, end), lambda b: b[2] >= O)
    out["back_open"] = window(day, back and back[0])
    det["t_back"] = back[0] if back else None
    if not back:
        out["at_open"] = "Never came back"
        rep.append("Never traded back at the 8:30 open by 16:00")
    else:
        so_far = lo(nq.stream(day.t(8, 30), back[0]))
        later = nq.stream(back[0], end)
        e_wick = first(later, lambda b: b[2] > H1)
        answers = []
        for ref in (so_far, L1):
            e_main = first(later, lambda b, r=ref: b[3] < r)
            if e_wick and e_main and e_wick[0] == e_main[0]:
                answers.append(None)
            elif e_wick and (not e_main or e_wick[0] < e_main[0]):
                answers.append("Broke through")
            elif e_main:
                answers.append("Swept & resumed")
            else:
                answers.append("Chopped around")
        out["at_open"] = answers[0] if answers[0] == answers[1] and answers[0] else None
        if out["at_open"] is None:
            warn.append(f"At the open: ambiguous ({answers}) - decide on the chart")
        rep.append(f"Back at the open {ny(back[0])} -> {out['back_open']}; then 1-min {W['wick']} taken "
                   f"{ny(e_wick[0]) if e_wick else 'never'} -> {out['at_open']}")

    # Liquidity
    sess = sessions(d["nq1m"])
    highs, lows = levels(d["nq1m"], day, sess, "high"), levels(d["nq1m"], day, sess, "low")
    out["liq_wick"] = biggest(highs, lambda v: wick_ext > v)
    out["liq_main"] = biggest(lows, lambda v: main_ext < v)
    for label, lv, test in (("wick", highs, lambda v: wick_ext > v), ("main", lows, lambda v: main_ext < v)):
        parts = [f"{n.replace(' high/low', '')} {P(x['value'])} "
                 + ("intact" if x["intact"] else f"gone {ny(x['taken_at'], '%d %b %H:%M')}")
                 + (" TAKEN" if x["intact"] and test(x["value"]) else "") for n, x in lv.items()]
        rep.append(f"{label} side ({W[label]}s): " + " | ".join(parts)
                   + f" -> {out['liq_' + label]}")

    # First 1m FVG of the main move: its middle candle must make a new low of the move
    fvg = None
    for i in range(15):
        mid = day.t(8, 30 + i)
        a, b, c = m1.get(mid - 60000), m1[mid], m1.get(mid + 60000)
        prior = [m1[day.t(8, 30 + j)][3] for j in range(i)]
        if a and c and a[3] > c[2] and (not prior or b[3] < min(prior)):
            fvg = (a, b, c)
            break
    if fvg is None:
        out["fvg"] = "No FVG"
        rep.append("1m FVG: none whose middle candle extends the move")
    else:
        a, b, c = fvg
        near, far, c3_close = c[2], a[3], c[0] + 60000
        det["fvg"] = {"near": near, "far": far, "c3_close": c3_close}
        ent = first(nq.stream(c3_close, end), lambda x: x[2] >= near)
        if not ent:
            out["fvg"] = "Never came back"
        else:
            low_before = lo(nq.stream(day.t(8, 30), ent[0]))
            closes = [x for x in d["nq1m"] if ent[0] // 60000 * 60000 <= x[0] < end]
            close_far = first(closes, lambda x: x[4] > far)
            new_low = first(nq.stream(ent[0], end), lambda x: x[3] < low_before)
            failed = close_far and (not new_low or close_far[0] + 60000 <= new_low[0])
            out["fvg"] = "Came back & failed (IFVG)" if failed else "Came back & held"
            det["fvg"].update(first_touch=ent[0], close_far=close_far[0] if close_far else None)
        rep.append(f"1m FVG {ny(a[0], '%H:%M')}/{ny(b[0], '%H:%M')}/{ny(c[0], '%H:%M')} near {P(near)} far {P(far)}; "
                   f"first return {ny(ent[0]) if ent else 'never'}; first 1m close past the far edge "
                   f"{ny(close_far[0], '%H:%M') if ent and close_far else 'none'} -> {out['fvg']}")

    # HTF PD array at the main-move extreme
    since = {15: sess[prior_sessions(sess, day)[-1]][0][0], 60: day.t(18, days=-9), 240: day.t(18, days=-26)}
    hits = []
    for tf in (15, 60, 240):
        bars = d[f"nq{tf}"]
        if not bars or bars[0][0] > since[tf]:
            raise ValueError(f"{tf}m bars must start by {ny(since[tf], '%d %b %H:%M')}")
        for arr in pd_arrays(bars, tf, since[tf], day.t(8, 30)):
            if arr["valid"] and arr["lo"] <= main_ext <= arr["hi"]:
                hits.append({**arr, "tf": tf})
    kinds = [k for k in ("FVG", "Order block", "Breaker") if any(h["kind"] == k for h in hits)]
    out["pda"] = kinds[0] if kinds else "No"
    tf_name = {15: "15m", 60: "1H", 240: "4H"}
    rep.append("HTF PD arrays containing the extreme: " + (", ".join(
        f"{tf_name[h['tf']]} {h['kind']} {P(h['lo'] if sign == 1 else h['hi'])}-{P(h['hi'] if sign == 1 else h['lo'])} "
        f"({ny(h['t'], '%d %b %H:%M')})" for h in hits) or "none") + f" -> {out['pda']}")

    # SMT with ES
    es_lows = levels(d["es1m"], day, sessions(d["es1m"]), "low")
    es_ext = lo([b for b in d["es1m"] if day.t(8, 30) <= b[0] < day.t(8, 45)])
    both = [n for n in LIQ_ORDER if lows[n]["intact"] and es_lows[n]["intact"]]
    div = [n for n in both if (main_ext < lows[n]["value"]) != (es_ext < es_lows[n]["value"])]
    out["smt"] = "Yes" if div else "No"
    rep.append(f"SMT: ES {W['main']} by 8:45 {P(es_ext)}; levels intact in both: "
               + ", ".join(f"{n.replace(' high/low', '')} NQ {'took' if main_ext < lows[n]['value'] else 'no'} / "
                           f"ES {'took' if es_ext < es_lows[n]['value'] else 'no'}" for n in both)
               + f" -> {out['smt']}")

    # Setups: the first one to trigger goes in the row
    cands = []
    if fvg:
        near, far, c3_close = det["fvg"]["near"], det["fvg"]["far"], det["fvg"]["c3_close"]
        touch = first(nq.stream(c3_close, end), lambda x: x[2] >= near)
        if touch:
            r, t_exit = walk(nq.stream(touch[0], end), "short", near, far + TICK, L1)
            cands.append(("A Continuation", touch[0], r, f"A: entry {P(near)} at {ny(touch[0])}, stop {P(far + TICK)}, "
                                                         f"target {P(L1)} -> {r}R at {ny(t_exit) if t_exit else '-'}"))
        context = out["liq_main"] in KEY_LEVELS or out["pda"] != "No"
        trig = first([x for x in d["nq1m"] if c3_close <= x[0] < day.t(9, 30)], lambda x: x[4] > far)
        if context and trig:
            fill = first(nq.stream(trig[0] + 60000, end), lambda x: x[3] <= far)
            t1 = first(nq.stream(trig[0] + 60000, end), lambda x: x[2] >= O)
            if fill and (not t1 or fill[0] < t1[0]):
                r1, _ = walk(nq.stream(fill[0], end), "long", far, L1 - TICK, O)
                r2, _ = walk(nq.stream(fill[0], end), "long", far, L1 - TICK, H1)
                det["B"] = {"r_t1": r1, "r_t2": r2}
                cands.append(("B Reversal", fill[0], None, f"B: entry {P(far)} at {ny(fill[0])} after the {ny(trig[0], '%H:%M')} "
                                                           f"close past the FVG, stop {P(L1 - TICK)} -> T1 {P(O)}: {r1}R, "
                                                           f"T2 {P(H1)}: {r2}R"))
    if back:
        back_min = back[0] // 60000 * 60000
        pre = [x for x in d["nq1m"] if day.t(8, 31) <= x[0] < back_min]
        swings = [pre[i] for i in range(1, len(pre) - 1) if pre[i][3] < pre[i - 1][3] and pre[i][3] < pre[i + 1][3]]
        wick_break = first(nq.stream(day.t(8, 31), end), lambda x: x[2] > H1)
        last_min = wick_break[0] // 60000 * 60000 if wick_break else day.t(15, 59)
        if swings:
            sw = swings[-1][3]
            trig = first([x for x in d["nq1m"] if back_min <= x[0] <= last_min], lambda x: x[4] < sw)
            if trig:
                sweep = hi(nq.stream(back[0], trig[0] + 60000))
                r, t_exit = walk(nq.stream(trig[0] + 60000, end), "short", trig[4], sweep + TICK, L1)
                cands.append(("C Open sweep", trig[0] + 60000, r, f"C: entry {P(trig[4])} at {ny(trig[0] + 60000)}, stop "
                                                                 f"{P(sweep + TICK)}, target {P(L1)} -> {r}R"))
                warn.append("Setup C triggered: its mechanics have not been checked on a real day yet - confirm on the chart")
        rep.append(f"C: last 1m swing {W['main']} before the return: {P(swings[-1][3]) if swings else 'none'}; "
                   + ("triggered" if any(k[0].startswith("C") for k in cands) else "not triggered"))
    firsts = [first([x for x in d["nq1m"] if day.t(8, 31) <= x[0] < end], p)
              for p in (lambda x: x[2] > H1, lambda x: x[3] < L1)]
    if any(f and day.t(9, 30) <= f[0] < day.t(11) for f in firsts):
        warn.append("Setup D candidate (a 1-min side was first taken 9:30-11:00) - check MSS + FVG on the chart")
    cands.sort(key=lambda k: k[1])
    rep += [k[3] for k in cands]
    if cands:
        out["setup"], out["r"] = cands[0][0], cands[0][2]
        if cands[0][0].startswith("B"):
            warn.append("Setup B is first: R depends on the exit (T1 vs T2) - pending the owner's decision")
        notes += [f"Setup {k[0]} also triggered" for k in cands[1:]]
    else:
        out["setup"], out["r"] = "None", None
    return out, rep, notes, warn, det


# ------------------------------------------------------------------ all columns
def analyze(date: dt.date, data: dict, main: str, cpi: str | None = None) -> dict:
    if main not in ("Up", "Down"):
        raise ValueError("main must be Up or Down (the sheet's Main Move)")
    day = Day(date)
    nq = Series(data["nq1m"], data["nq1s"])
    if nq.s1_start > day.t(8, 30) or nq.s1_end < day.t(8, 46):
        raise ValueError("1s bars must cover at least 8:30-8:45")
    m1 = nq.by_t
    O, H1, L1, C1 = m1[day.t(8, 30)][1:5]
    sec = [b for b in data["nq1s"] if day.t(8, 30) <= b[0] < day.t(8, 31)]
    if (sec[0][1], hi(sec), lo(sec), sec[-1][4]) != (O, H1, L1, C1):
        raise ValueError("1s bars of the 8:30 minute don't add up to the 1m bar")
    t_hi = min(b[0] for b in sec if b[2] == H1)
    t_lo = min(b[0] for b in sec if b[3] == L1)
    values, rep, warn = {}, [], []
    rep.append(f"8:30 candle O {fmt(O)} H {fmt(H1)} ({ny(t_hi)}) L {fmt(L1)} ({ny(t_lo)}) C {fmt(C1)}")
    guess = "Down" if t_hi < t_lo else "Up" if t_lo < t_hi else None
    if guess != main:
        warn.append(f"Main Move {main} but the 1-min {'extremes printed in the same second' if guess is None else guess.lower() + ' order'}"
                    " - check the sheet")
    if cpi:
        values["cpi"] = cpi

    c15 = [m1[day.t(8, 30 + i)] for i in range(15)]
    closes = []
    for key, bs in (("close1", c15[:1]), ("close5", c15[:5]), ("close15", c15)):
        values[key], pos = third(bs[-1][4], hi(bs), lo(bs))
        closes.append(f"{key[5:]}m {pos:.3f} {values[key]}")
    rep.append("Close location: " + " | ".join(closes))
    after = [b for b in data["nq1m"] if day.t(8, 31) <= b[0] < day.t(16)]
    fh, fl = first(after, lambda b: b[2] > H1), first(after, lambda b: b[3] < L1)
    values["high_when"], values["low_when"] = window(day, fh and fh[0]), window(day, fl and fl[0])
    rep.append(f"1-min high first taken in the {ny(fh[0], '%H:%M') + ' bar' if fh else '- (never)'} -> "
               f"{values['high_when']}; 1-min low {ny(fl[0], '%H:%M') + ' bar' if fl else '- (never)'} -> {values['low_when']}")
    mid = m1[day.t(0)][1]
    values["midnight"] = "Above (premium)" if O > mid else "Below (discount)" if O < mid else None
    if values["midnight"] is None:
        warn.append("8:30 open equals the midnight open")
    rep.append(f"Midnight open {fmt(mid)} vs 8:30 open {fmt(O)} -> {values['midnight']}")
    values["bias"], why = daily_bias(sessions(data["nq1m"]), day)
    rep.append(f"Daily bias: {why} -> {values['bias']}")

    sign = 1 if main == "Down" else -1
    d = data if sign == 1 else {k: mirror(v) for k, v in data.items()}
    dd, rep_dd, notes, warn_dd, det = analyze_down(day, d, sign)
    values.update(dd)
    rep += rep_dd
    warn += warn_dd

    for key, val in values.items():
        if key in OPTIONS and val is not None and val not in OPTIONS[key]:
            raise ValueError(f"{key}={val!r} is not a dropdown option")
    return {"date": date.isoformat(), "main": main, "values": values, "report": rep, "notes": notes,
            "warnings": warn, "details": det}


def load(date: dt.date, data_dir: Path = DATA_DIR) -> dict:
    folder = Path(data_dir) / date.isoformat()
    return {k: sorted(json.loads((folder / f).read_text())) for k, f in FILES.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, type=dt.date.fromisoformat, help="release date, e.g. 2026-07-14")
    ap.add_argument("--main", required=True, choices=["Up", "Down"], help="Main Move from the sheet (column E)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--cpi", choices=bt.CPI, help="CPI vs forecast, if already known")
    g.add_argument("--cpi-numbers", nargs=4, metavar=("CPI", "CPI_FC", "CORE", "CORE_FC"),
                   help="m/m actual and forecast, e.g. 0.4 0.4 0.3 0.2")
    ap.add_argument("--data", type=Path, default=DATA_DIR)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    cpi = args.cpi or (classify_cpi(*args.cpi_numbers) if args.cpi_numbers else None)
    res = analyze(args.date, load(args.date, args.data), args.main, cpi)
    print("\n".join(res["report"]))
    print("\nVALUES:")
    for k, v in res["values"].items():
        print(f"  {k:<10} {v}")
    for n in res["notes"]:
        print("NOTE:", n)
    for w in res["warnings"]:
        print("CHECK:", w)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.date.isoformat()}.json"
    path.write_text(json.dumps(res, indent=1))
    print("wrote", path)


if __name__ == "__main__":
    main()
