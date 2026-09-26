#!/usr/bin/env python3
"""Download the FX Replay bars that rules.py needs for one CPI release.

Logs in with a headless browser, opens an existing FX Replay backtesting session
(the chart's own data requests carry the auth headers), then calls the same data
endpoint. Credentials come from the environment and are never printed or saved:
FXREPLAY_ACCOUNT (or FXREPLAY_EMAIL) and FXREPLAY_PASSWORD.

FX Replay allows 5 activated devices per account and every new browser profile
counts as one, so the browser profile is kept in backtest/.browser/fxreplay
(git-ignored; it holds the login cookie). Reuse it instead of deleting it.

    python backtest/fxreplay_fetch.py --date 2026-07-14

Writes backtest/data/<date>/{nq_1m,nq_1s,es_1m,nq_15,nq_60,nq_240}.json, each a
list of [time_ms_utc, open, high, low, close, volume, null] (bar open times).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "backtest" / "data"
PROFILE_DIR = ROOT / "backtest" / ".browser" / "fxreplay"
LOGIN = "https://app.fxreplay.com/en-US/login"
DASHBOARD = "https://app.fxreplay.com/en-US/auth/testing/dashboard"
API = "https://awf.fxreplay.com/archives-zip-opt"
SESSION_NAME = "CPI 11 Sep 2026 - NQ check (Hoplite)"
# Appcues onboarding overlay intercepts clicks.
HIDE_OVERLAY = "appcues-experience-container, appcues-container, #appcues-container {display: none !important;}"
NQ, ES = "CME_MINI:NQ1", "CME_MINI:ES1"


def ts(date, h, mi=0, days=0):
    d = date + dt.timedelta(days=days)
    return int(dt.datetime(d.year, d.month, d.day, h, mi, tzinfo=NY).timestamp() * 1000)


def ny(ms):
    return dt.datetime.fromtimestamp(ms / 1000, NY).strftime("%a %d %b %Y %H:%M:%S")


class FXReplay:
    def __init__(self, page):
        self.page = page
        self.headers = None
        self.current = None  # the session's replay time; data after it is not served
        page.context.on("request", self._capture)

    def _capture(self, req):
        if "/archives-zip-opt/" not in req.url:
            return
        try:
            h = req.all_headers()
        except Exception:
            h = req.headers
        if h.get("authorization"):
            self.headers = {k: v for k, v in h.items() if k in ("authorization", "x-session-id", "x-tab-id", "accept")}
            q = parse_qs(urlsplit(req.url).query)
            if "currentDate" in q:
                self.current = int(q["currentDate"][0])

    def login(self, email, password):
        p = self.page
        p.goto(DASHBOARD, wait_until="domcontentloaded", timeout=90000)
        p.wait_for_timeout(8000)
        if "/login" in p.url:
            p.locator("input[placeholder='Email']").fill(email, timeout=60000)
            p.locator("input[type='password']").fill(password)
            p.get_by_role("button", name="Sign in", exact=True).click()
            p.wait_for_url(lambda u: "/auth/" in u or "/device-limit" in u, timeout=90000)
        if "/device-limit" in p.url:
            raise RuntimeError("FX Replay says this account is at its device limit (5). The owner has to sign out an "
                               "old device (e.g. an unused 'Linux - Google Chrome') in FX Replay - don't do it for them.")

    def open_session(self, name):
        p = self.page
        if "/dashboard" not in p.url:
            p.goto(DASHBOARD, wait_until="domcontentloaded", timeout=90000)
        p.add_style_tag(content=HIDE_OVERLAY)
        p.get_by_text(name, exact=True).first.click(timeout=60000)
        p.wait_for_url("**/sessions/**", timeout=90000)
        p.add_style_tag(content=HIDE_OVERLAY)
        deadline = time.time() + 120
        while (self.headers is None or self.current is None) and time.time() < deadline:
            p.wait_for_timeout(1000)
        if self.headers is None or self.current is None:
            raise RuntimeError("the chart did not request any data - is the session loading?")

    def _request(self, symbol, res, frm, to, limit):
        url = f"{API}/{symbol}/{res}?to={to}&limit={limit}&from={frm}&currentDate={self.current}"
        headers = {**self.headers, "x-request-id": str(uuid.uuid4())}
        status, text = self.page.evaluate(
            "async ([u, h]) => { const r = await fetch(u, {headers: h, credentials: 'include'});"
            " return [r.status, await r.text()]; }", [url, headers])
        if status != 200:
            raise RuntimeError(f"{symbol} {res}: HTTP {status}")
        self.page.wait_for_timeout(250)
        return json.loads(text)

    def get(self, symbol, res, frm, to, limit):
        # The newest bar of every response is merged with everything up to the session's replay time.
        return [b for b in sorted(self._request(symbol, res, frm, to, limit))[:-1] if b[0] < to]

    def bars(self, symbol, res, start, end, step_hours, limit=1500):
        """Bars before `end`, from at least `start`; each request returns `limit` bars before its `to`."""
        out = {}
        step = step_hours * 3600 * 1000
        for to in list(range(start, end, step)) + [end]:
            for b in self.get(symbol, res, to - 1, to, limit):
                if b[0] in out and out[b[0]][:5] != b[:5]:
                    raise RuntimeError(f"{symbol} {res}: overlapping responses disagree at {ny(b[0])}")
                out[b[0]] = b
        return [out[k] for k in sorted(out)]

    def seconds(self, symbol, start, end):
        out, t = {}, end
        while t > start:
            got = [b for b in self.get(symbol, "1S", start, t, 1500) if b[0] >= start]
            if not got:
                break
            out.update({b[0]: b for b in got})
            t = got[0][0]
        return [out[k] for k in sorted(out)]


def aggregate(bars):
    return [bars[0][1], max(b[2] for b in bars), min(b[3] for b in bars), bars[-1][4]]


def check(date, got):
    """Print coverage and consistency checks; returns a list of problems."""
    problems = []
    m1 = {b[0]: b for b in got["nq_1m"]}
    if ts(date, 8, 30) not in m1:
        problems.append("no NQ 1m bar at 8:30")
    day = [b for b in got["nq_1m"] if ts(date, 18, days=-1) <= b[0] < ts(date, 16)]
    gaps = [(ny(a[0]), ny(b[0])) for a, b in zip(day, day[1:]) if b[0] - a[0] > 60000]
    if gaps:
        problems.append(f"gaps in the release-day NQ 1m bars: {gaps[:3]}")
    bad = 0
    for m in range(ts(date, 8, 16), ts(date, 10, 1), 60000):
        secs = [b for b in got["nq_1s"] if m <= b[0] < m + 60000]
        if secs and m in m1 and aggregate(secs) != m1[m][1:5]:
            bad += 1
    if bad:
        problems.append(f"{bad} minutes where NQ 1s bars don't add up to the 1m bar")
    for name, minutes in (("nq_15", 15), ("nq_60", 60), ("nq_240", 240)):
        for b in got[name]:
            if b[0] < got["nq_1m"][0][0] or b[0] + minutes * 60000 > ts(date, 8, 30):
                continue
            mins = [m1[t] for t in range(b[0], b[0] + minutes * 60000, 60000) if t in m1]
            if mins and aggregate(mins) != b[1:5]:
                problems.append(f"{name} bar {ny(b[0])} doesn't match the 1m bars")
                break
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, type=dt.date.fromisoformat, help="release date, e.g. 2026-07-14")
    ap.add_argument("--session", default=SESSION_NAME, help="name of an existing FX Replay session")
    ap.add_argument("--out", type=Path, default=DATA_DIR)
    args = ap.parse_args(argv)
    email = os.environ.get("FXREPLAY_ACCOUNT") or os.environ.get("FXREPLAY_EMAIL")
    password = os.environ.get("FXREPLAY_PASSWORD")
    if not email or not password:
        sys.exit("set FXREPLAY_ACCOUNT (or FXREPLAY_EMAIL) and FXREPLAY_PASSWORD")

    from playwright.sync_api import sync_playwright

    d = args.date
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=True, args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1600, "height": 1000}, locale="en-US", timezone_id="America/New_York")
        page = browser.pages[0] if browser.pages else browser.new_page()
        fx = FXReplay(page)
        fx.login(email, password)
        fx.open_session(args.session)
        end = ts(d, 17, 5)
        if fx.current < end:
            browser.close()
            sys.exit(f"session replay time is {ny(fx.current)}: create a newer FX Replay session (see HANDOFF.md)")
        got = {
            "nq_1m": fx.bars(NQ, "1", ts(d, 18, days=-16), end, 12),
            "es_1m": fx.bars(ES, "1", ts(d, 18, days=-16), end, 12),
            "nq_1s": fx.seconds(NQ, ts(d, 8, 16), ts(d, 10, 1)),
            "nq_15": fx.bars(NQ, "15", ts(d, 18, days=-6), end, 72),
            "nq_60": fx.bars(NQ, "60", ts(d, 18, days=-11), end, 240),
            "nq_240": fx.bars(NQ, "240", ts(d, 18, days=-29), end, 600),
        }
        browser.close()
    folder = args.out / d.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    for name, bars in got.items():
        (folder / f"{name}.json").write_text(json.dumps(bars))
        print(f"{name:<7} {len(bars):>6} bars  {ny(bars[0][0])} -> {ny(bars[-1][0])}")
    problems = check(d, got)
    print("checks:", "OK" if not problems else "")
    for pr in problems:
        print("  PROBLEM:", pr)
    print("wrote", folder)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
