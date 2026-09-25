# Handoff: CPI $NQ backtest (read this first)

Status as of 25 Sep 2026. This is everything the next assistant needs to continue. Rules: [backtest/RULES.md](backtest/RULES.md).
Template: [README.md](README.md).

## The project

The owner (GitHub `narwana1`) backtests **US CPI releases on NQ futures** and trades **ICT concepts**. Each CPI release
is one row in a Google Sheet: how price reacted at 8:30 NY (wick, main move, how far in 15 s / 30 s / 1 min), what
happened after the first minute (when the 1-minute candle's high/low got taken, the return to the 8:30 open, pullback
depth), ICT context (bias, liquidity, PD arrays, FVGs, SMT) and which setup triggered with its result in R. The goal is
to find repeatable entries.

Working with the owner:
- Asks for a sheet that is simple and easy to read later.
- Repeats "make no mistakes": use fixed rules, verify every value independently, and verify the sheet after writing.
- Messages are short and informal. When a request is ambiguous, state the reading you picked (e.g. "Aug 2026 CPI" was
  taken to mean the release in August, i.e. July data).

## Where things are

| What | Where | Notes |
|---|---|---|
| Working sheet "CPI_NQ_Backtest_Template" (tabs `CPI Log`, `Stats`, `Guide`) | Ask the owner for the link, or read `CPI_SHEET_ID` if it's in the environment | **Not in this repo on purpose**: the repo is public and anyone with the link can edit. Locale en_US. Edits made through the link show as "Anonymous". |
| Original data sheet (tab `CPI data $NQ`, A–K) | Ask the owner | The owner's first backtest. Source of CPI Log rows 4–84, A–K. Read only. |
| FX Replay account (market data, charts) | Email: env `FXREPLAY_ACCOUNT` (already set). Password: env `FXREPLAY_PASSWORD` (not set; ask the owner to add it as a secret) | Pro **trial**, day 4 of 5 on 24 Sep 2026, so access may lapse. **At the device limit (5/5) on 25 Sep**: see "Blockers". |
| FX Replay session used | "CPI 11 Sep 2026 - NQ check (Hoplite)" (NQ1, legacy chart) | Its replay time is 14 Sep 2026 13:09, so it serves data for any release up to 11 Sep 2026. Create a newer session for later releases. It holds the annotated 11 Sep and 12 Aug drawings. The owner's other session "API Test Session EURUSD" was never touched. |
| Template generator / verifier | `tools/` (PR #2) | `build_template.py` builds the xlsx; `verify_template.py` recalculates it in LibreOffice and checks every formula. |
| Backtest tooling | `backtest/` (this PR) | `rules.py`, `fxreplay_fetch.py`, `sheet.py`, `test_rules.py`, `RULES.md`. |

Sheet layout: CPI Log headers are on rows 1–3 and data on rows 4–503. **Row = original sheet row + 2**: row 4 = 14 Jan 2020 … row 74 = "Canceled"
(the release due in Nov 2025 was not published) … row 82 = 14 Jul 2026, row 83 = 12 Aug 2026, row 84 = 11 Sep 2026. Column letters and
dropdown values are defined in `tools/build_template.py` (`COLUMNS`); dropdown cells only accept those exact strings.

## What has been done

1. **Template** (PR #2): the sheet design, the auto columns (Day, Move vs data, Outcome, First side taken), 13 Stats
   tables and the Guide. The owner imported it into Google Sheets.
2. **Migration**: the owner's 81 releases (14 Jan 2020 → 11 Sep 2026) were pasted into CPI Log A–K (values only),
   verified cell by cell. The 66 "Same" cells in 30sec/1min were replaced by the number they meant. Three of them
   followed an "… opposite" text, so the text was repeated (1min on 13 Jun 2023, 14 Aug 2024 and 10 Apr 2026). The 5
   "opposite" texts and the "N/A" on 10 Apr 2020 were kept as typed. A74's date format was restored after the paste.
3. **Rows 84 (11 Sep 2026) and 83 (12 Aug 2026)**: every new column filled from FX Replay 1-second/1-minute data with
   the rules in RULES.md. A separate reviewer with its own code re-derived every value, and after writing, a fresh
   export showed only the intended cells changed and all 333 Stats cells matched a Python recalculation. The values
   are listed in RULES.md → Reference results.
4. **Chart links** (column AG) are public FX Replay snapshot PNGs of the annotated 1m chart (levels, FVGs, trades).
5. The 1m-FVG rule was tightened while doing row 83 (the middle candle must make a new low/high of the move). Row 84
   already satisfied it, so no change was needed there.

Everything else in the new columns (rows 4–82) is empty. The owner's own columns A–K are theirs: never change them.

## Blockers and open questions (ask the owner)

1. **FX Replay device limit.** The account allows 5 activated devices and shows 5/5: Windows Chrome, Windows Firefox
   (probably the owner's) and three "Linux - Google Chrome". Those three are almost certainly the earlier sandbox
   logins; the browser profile was deleted after each session, so every login became a new device. Nobody can sign in on
   a new device until one is signed out. **The owner should sign them out** (FX Replay → device list, or the
   device-limit page after logging in). "Sign out of all devices" plus a password change is the safest option, because
   the password was pasted in chat. Don't sign devices out yourself. `fxreplay_fetch.py` now keeps one saved profile in
   `backtest/.browser/fxreplay` so it only uses one device.
2. **Password security.** The owner pasted the FX Replay password in chat and was told to change it. Never reuse it from
   chat history; ask for `FXREPLAY_PASSWORD` as an environment secret.
3. **Setup B on 11 Sep.** B also triggered (long 29353.5 at 8:38:02 → 29399.5 at 8:49:13, +0.31R at T2 / +0.21R at T1),
   but a row holds one setup, so the first one (A, −1R) was recorded. The owner was asked whether to put B in Notes or
   add a second setup column. **No answer yet.**
4. **Guide wording.** It was offered to add "the middle candle must make a new low/high of the move" to the Guide and
   the 1m FVG column note. Not done yet.
5. **July.** The owner first asked for "July & Aug 2026 CPI", then only "Aug". 14 Jul 2026 (row 82) is not done. Confirm
   before doing it or any older rows.
6. **Older rows.** Whether FX Replay has 1-second NQ data for old years is unknown. `rules.py` requires it for 8:30–8:45.

## How to do the next release (e.g. row 82, 14 Jul 2026)

```bash
pip install -r requirements.txt && python -m playwright install --with-deps chromium
export CPI_SHEET_ID=...        # from the owner
export FXREPLAY_PASSWORD=...   # environment secret; FXREPLAY_ACCOUNT is already set

python backtest/fxreplay_fetch.py --date 2026-07-14                    # bars -> backtest/data/2026-07-14/ (checks included)
python backtest/rules.py --date 2026-07-14 --main Up --cpi-numbers <cpi> <cpi fc> <core> <core fc>   # --main = column E (Up for 14 Jul)
#   read the report, NOTE and CHECK lines; get the values re-derived independently (e.g. a reviewer with its own code)
python backtest/sheet.py snapshot --out backtest/out/pre.xlsx
python backtest/sheet.py fill --row 82 --values backtest/out/2026-07-14.json --dry-run
python backtest/sheet.py fill --row 82 --values backtest/out/2026-07-14.json --link <chart snapshot url>
python backtest/sheet.py check --pre backtest/out/pre.xlsx --row 82 --values backtest/out/2026-07-14.json --link <url>
python backtest/test_rules.py                                          # still reproduces rows 83/84 (needs their data)
```

`sheet.py fill` never writes columns A–K or the automatic columns and skips filled cells unless `--overwrite`.
Market data and exports stay in `backtest/data/` and
`backtest/out/` (git-ignored; FX Replay data must not be published).

**Chart link.** Open the FX Replay session, then run this in the chart iframe (the frame named `tradingview_*`):
`const c = window.tradingViewApi.activeChart()`, then `await c.setVisibleRange({from, to})` (seconds),
`c.createShape({time, price}, {shape: 'text', text, overrides: {...}})` and
`c.createMultipointShape([{time, price}, {time, price}], {shape: 'rectangle' | 'trend_line' | 'long_position' | 'short_position', ...})`.
`await window.tradingViewApi.takeScreenshot()` uploads the chart and returns `https://fxr-snapshots.s3.amazonaws.com/<id>.png`,
which goes in column AG. Hide the Volume study for the picture and turn it back on after. `window.tradingViewApi.saveChartToServer(() => {}, () => {})`
forces the drawings to save.

## Things that bit before

- **FX Replay data endpoint** (what `fxreplay_fetch.py` uses):
  `https://awf.fxreplay.com/archives-zip-opt/<SYMBOL>/<RES>?to=<ms>&limit=<n>&from=<ms>&currentDate=<ms>` with the
  chart's `authorization`, `x-session-id` and `x-tab-id` headers.
  - RES = `1S`, `1`, `15`, `60`, `240`, `1D`. The response holds `limit` bars up to `to`, newest first.
  - **The newest bar is merged with everything up to the session's replay time**, so drop it.
  - 1-second bars add up exactly to the 1-minute bars, and those to the 15m/1H/4H bars (4H anchored at 18:00 NY).
- **FX Replay UI**:
  - An Appcues onboarding overlay swallows clicks. Hide it with CSS: `appcues-experience-container {display:none}`.
  - FX Replay's own "Go To" moves the replay position; use the TradingView go-to-date button or `setVisibleRange` instead.
  - Pressing Escape in the new-session wizard closes the whole wizard.
- **Google Sheets automation**:
  - Select cells through the Name Box (`#t-name-box`) and read them from the formula bar (`#t-formula-bar-input`).
  - Set dropdown cells by selecting the cell, pressing Enter and clicking the exact option. A multi-cell paste across
    validated cells was rejected once.
  - Pasting a URL with Ctrl+Shift+V silently failed once, so type it instead.
  - The pullback column's format makes 97 show as `9700%` in the formula bar.
  - Every export differs byte-wise, so compare cell content, not files.
- **ForexFactory** blocks headless browsers (Cloudflare). **Yahoo's** chart API answered 429.
- **Shell**: `pkill -f <pattern>` also kills the shell command that contains the pattern. Use `ps aux | grep '[p]attern'`.

## Never commit

Passwords, the FX Replay email, sheet links or IDs, `backtest/.browser/` (login cookies), `backtest/data/` (FX Replay
data) or the owner's backtest numbers beyond what is already in RULES.md.
