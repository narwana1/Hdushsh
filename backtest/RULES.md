# Backtest rules: what each CPI Log column means, exactly

These are the rules `backtest/rules.py` implements. They produced rows 83 (12 Aug 2026) and 84 (11 Sep 2026), and
`backtest/test_rules.py` checks the script still reproduces those rows. Keep the rules fixed so rows stay comparable.
If a rule has to change, re-run every row that was already filled.

## Data, time and names

- Prices: FX Replay continuous futures `CME_MINI:NQ1` (NQ) and `CME_MINI:ES1` (ES). Times: New York.
  Bars are `[open time (ms, UTC), open, high, low, close, volume]`. Tick = 0.25.
- 1-second bars cover 8:16–10:00 on the release day. Anything that walks price over time uses 1-second bars while they
  exist and 1-minute bars after 10:00.
- CME session = 18:00 the evening before → 17:00. Only days with bars count as sessions: a Tuesday's previous session
  (D-1) is Monday and D-2 is Friday. Holiday-shortened sessions count.
- **8:30 candle** = the 1-minute bar 8:30:00–8:30:59. **O / H / L / C** = its open, high, low and close.
  **1-min high / low** = H / L.
- **Main move** comes from the sheet (column E, the owner's call). The rules below are written for a **Down** main move.
  For **Up**, mirror them (swap high/low, above/below). The script literally negates every price on Up days.
- **Main-move start** = the last second, at or before the second that printed L, whose high was at or above O.
  **Wick high** = the highest price from 8:30:00 through that second.
  **Main-move low** = the lowest low of the 1-minute bars 8:30–8:44.
- **Time windows** (sheet dropdowns) go by the time of the first trade. 0-15 sec = 8:30:00–8:30:14 · 15-30 sec ·
  30-60 sec · 1-5 min = 8:31:00–8:34:59 · 5-15 min = 8:35:00–8:44:59 · 15-60 min = 8:45:00–9:29:59 · 9:30-11:00 ·
  11:00-16:00 · Not by 16:00.

## Columns

| Column | Rule |
|---|---|
| CPI vs forecast | CPI m/m and Core CPI m/m, actual vs forecast (ForexFactory history). If ForexFactory is blocked, use the BLS release for the actual and the consensus reported by Bloomberg / Dow Jones / Reuters-type sources. Both higher (or one higher, one equal) = Hotter · both lower (or one lower, one equal) = Cooler · both equal = In line · one higher, one lower = Mixed. |
| 1m / 5m / 15m candle close | (close − low) / (high − low) of the 8:30 candle, of 8:30–8:34 and of 8:30–8:44 (built from 1-minute bars). Below 1/3 = Bottom, below 2/3 = Middle, otherwise Top. |
| 1-min HIGH / LOW taken – when? | The first 1-minute bar from 8:31 that trades above H (below L), placed by the bar's start time. Not by 16:00 if none. |
| Deepest pullback % | Highest price from 8:31:00 until L breaks or 8:45, whichever comes first. (That high − L) / (O − L) × 100, rounded half up. 0 if L breaks at 8:31:00. |
| Back to 8:30 open – when? | The first trade at or above O after the main-move start. |
| At the open, price… | After that return: first trade above H = **Broke through**. First trade below the lowest price so far (8:30 up to the return) = **Swept & resumed**; this must agree with the answer using "below L", otherwise decide by hand. Neither by 16:00 = **Chopped around**. No return = **Never came back**. A tie inside one bar is left for a manual decision. |
| Daily bias | D-1 session vs D-2 session. D-1 close > D-2 high = Bullish · close < D-2 low = Bearish · traded above the D-2 high but closed inside (and didn't take the D-2 low) = Bearish · traded below the D-2 low but closed inside (and didn't take the high) = Bullish · otherwise No bias. **No body-size filter** (some indicator versions want a ≥ 50 % body; not used). |
| 8:30 open vs Midnight open | O compared with the open of the 00:00 1-minute bar. |
| Liquidity taken by wick / main move | Levels: **Pre-news** 7:00–8:29 · **Asia** 20:00–23:59 the evening before · **London** 2:00–4:59 · **Prev day** = the D-1 session · **Prev week** = the previous week's Mon–Fri sessions. A level only counts if nothing traded beyond it between the end of its window and 8:30. Wick = the biggest untouched high that the wick high went above. Main = the biggest untouched low that the main-move low went below. Size order: Prev week > Prev day > London > Asia > Pre-news. None if nothing qualifies. |
| HTF PD array at extreme | Bullish arrays on 15m / 1H / 4H (FX Replay bars; 4H opens 18:00, 22:00, 02:00 …) that **contain the main-move low**, were fully closed by 8:30 and whose first candle opened after the lookback start: 15m = start of the D-1 session, 1H = 18:00 nine days before, 4H = 18:00 26 days before. **FVG**: candle-1 high < candle-3 low (the zone is the gap), valid if no later low reached its top before 8:30. **Order block**: a down-close candle followed by an up-close candle, with a close above its high within 3 candles; zone = the full candle; valid if nothing later closed below its low. **Breaker**: an up-close candle followed by a down-close candle, a close below its low within 3 candles, later a close above its high; valid if nothing closed below its low after that. Pick FVG, then Order block, then Breaker; otherwise No. "Other" is never set automatically. |
| 1m FVG from main move | The first 3-candle bearish gap (candle-1 low > candle-3 high) whose middle candle is between 8:30 and 8:44 **and makes a new low of the move**, i.e. is lower than every 1-minute low since 8:30 (the 8:30 candle always qualifies). Near edge = candle-3 high, far edge = candle-1 low. Then take the first trade back at the near edge after candle 3 closes. None = Never came back. A 1-minute close above the far edge before a new low (below the lowest price before the return) = Came back & failed (IFVG). Otherwise Came back & held. No such gap = No FVG. |
| SMT with ES | The same five reference lows, computed separately for NQ and ES. Only levels untouched in both at 8:30 count. Yes if, by 8:45 (1-minute lows 8:30–8:44), one index took a level the other didn't; otherwise No. |
| Setup / Result (R) | The first setup to trigger, by entry time. R = reward ÷ risk, rounded to 2 decimals. Inside one bar the stop is checked before the target. |

### Setups (Down; mirror for Up)

- **A Continuation**: needs the 1m FVG. Limit sell at the near edge on the first touch after candle 3 closes. Stop 1 tick
  above the far edge, target L.
- **B Reversal**: needs the 1m FVG plus context: the main move took London / Prev day / Prev week or tapped an HTF PD
  array. Trigger = the first 1-minute close above the far edge before 9:30. Limit buy at the far edge after that close
  (void if price reaches O first). Stop 1 tick below L, T1 = O, T2 = H. **Open question:** which R to record when B is
  the first setup (T1, T2 or half/half) has not been decided (see HANDOFF.md).
- **C Open sweep**: after the return to O, take the last 3-candle swing low of the 1-minute bars from 8:31 to the minute
  before the return. Trigger = a 1-minute close below it, at or before the minute H is first taken. Entry at that close,
  stop 1 tick above the highest price since the return, target L. *Not yet exercised on a real day.*
- **D 9:30–11:00 raid**: only flagged, when a side of the 8:30 candle is taken for the first time between 9:30 and
  11:00. Check the MSS + FVG on the chart by hand.

## Reference results (the regression test)

| | Row 84 · 11 Sep 2026 | Row 83 · 12 Aug 2026 |
|---|---|---|
| CPI vs forecast | Hotter (CPI 0.4 vs 0.4, core 0.3 vs 0.2) | In line (0.1 vs 0.1, 0.2 vs 0.2) |
| 8:30 candle | O 29385 · H 29399.5 (8:30:00) · L 29204 (8:30:08) · C 29244.5 | O 29905.25 · H 29960 (8:30:00) · L 29750.25 (8:30:13) · C 29832 |
| Closes 1m / 5m / 15m | Bottom / Top / Top | Middle / Top / Top |
| High / low taken | 15-60 min (8:49:13) / Not by 16:00 | 15-60 min (9:19:51) / Not by 16:00 |
| Pullback | 97 (29379.5 at 8:40) | 119 (29935 at 8:42:52) |
| Back to open / at the open | 15-60 min (8:48:33) / Broke through | 1-5 min (8:34:40) / Broke through |
| Daily bias | Bearish (10 Sep closed 29143.25 < 9 Sep low 29333) | Bearish (11 Aug closed 29646.75 < 10 Aug low 29718.75) |
| Midnight | Above (premium), 29058.75 | Above (premium), 29694.75 |
| Liquidity wick / main | Pre-news (29399) / London (29215.5) | Pre-news (29932.25) / Pre-news (29805.5) |
| HTF PD array | FVG: 1H 29151.5–29215.5 and 4H 29171.5–29215.5 | Breaker: 1H 29718.25–29804.75 (15m ones too) |
| 1m FVG | 29309.75–29353.5 → failed (IFVG), 1m close above at 8:37 | No FVG (8:29 low 29862.5 < 8:31 high 29873.25) |
| SMT | No (ES also took its London and pre-news lows) | No (both took only their pre-news low) |
| Setup / R | A Continuation, −1 (short 29309.75 at 8:32:44, stopped 8:36:11); B also triggered: +0.21 (T1) / +0.31 (T2) | None |
