# Research log: searching for a 90% win-rate, 0.5R strategy on NQ / GC

All numbers below are produced by `make research` and `make strategy`. The raw outputs are in
[`research/`](research/) and [`strategy_results.md`](strategy_results.md).

## Definitions and protocol

- **Bracket.** The stop is `S` points from the fill and the target is `0.5 x S`. A trade
  counts as a **win only if the target fills first** (strict win rate). With no edge the
  expected win rate is 2/3, which is also the break-even point before costs.
- **Data.** NQ proxy: HistData NSXUSD 1-minute bars, 2010-11 to 2026-09. GC proxy: XAUUSD
  1-minute bars, 2009 to 2026-09. Both were validated against Yahoo futures hourly bars
  ([`data_validation.txt`](data_validation.txt)). Nasdaq-100 index daily bars cover 2000-2010.
- **Split.** Rules were selected only on data **before 2020-01-01**. 2020-01 to 2026-09 is
  out-of-sample (OOS). ^NDX daily bars for 2000-2010 are a second, untouched test period.
- **Costs and fills.**
  - $5 round trip.
  - 1 tick slippage on market entries and stops.
  - A target fills only if price trades through it by 1 tick.
  - A gap through a level fills at the worse open.
  - If stop and target are both touched in the same minute, the trade is a loss.
- **Ranking.** Variants were ranked by the lower 95% Wilson bound of the in-sample win rate.
  This penalises small samples.

## 1. Baseline: random entries (01)

Every day, enter long or short at 09:30 or 18:05 with stops of 0.25-2 ATR and no costs. Strict
win rates ranged from **61.1% to 71.1%**, around the theoretical 66.7%. Longs sit higher and
shorts lower because of upward drift. This confirms the engine and data: the benchmark any
real edge has to beat is about 2/3.

## 2. Rule scans (02, 03, 05) and what the in-sample leaders did out of sample (10)

| scan | variants | min IS trades | best IS WR | top-10 by IS: mean IS WR -> mean OOS WR | variants with IS WR >= 90% | ... of those with OOS WR >= 90% |
|---|---|---|---|---|---|---|
| daily signals (RSI2/3, IBS, down/up streaks, Bollinger z, 5-day extremes x trend filters x 2 entry times x 5 stop sizes x long/short) | 2530 | 100 | 81.0% | 77.8% -> 71.5% | 0 | 0 |
| intraday (fade/follow the move from the RTH open or prior close at 7 decision times x 5 thresholds x 5 stop sizes x 2 holding rules) | 2180 | 100 | 77.6% | 74.1% -> 69.2% | 0 | 0 |
| mean reversion + wide stops (3-8 ATR) | 230 | 30 | 90.3% | 84.5% -> 77.1% | 1 | 0 |

Across the scans, 99% of daily variants with at least 100 trades had in-sample win rates at or
below about 77%. The single variant at 90%+ in-sample was NQ RSI(2) < 5 with an 8-ATR stop,
on 31 trades. It won 73.7% on 19 OOS trades.

## 3. Wide stops (04): the only way drift alone pushes the win rate up

Always long, re-entering whenever flat, with a k x ATR stop:

| market | stop | trades (2010-26) | WR | IS WR | OOS WR | median hold |
|---|---|---|---|---|---|---|
| NQ | 5 ATR | 177 | 79.1% | 80.8% | 76.9% | 21 d |
| NQ | 8 ATR | 90 | 82.2% | 83.0% | 81.1% | 54 d |
| NQ | 10 ATR | 57 | 84.2% | 85.3% | 82.6% | 67 d |
| GC | 8 ATR | 64 | 87.5% | 84.4% | **90.6%** (32 trades, 95% CI 76-97%) | 45 d |

This is essentially buy-and-hold with a distant stop: the median is 11-14% below entry and some
stops are up to 32% away. The GC 2020-2026 figure
reflects gold's rally from about $1,500 to about $4,400. It is not repeatable skill: the same
rule won 84% in 2009-2019, a period that includes gold's 2012-2015 bear market.

## 4. Pre-registered candidates (06) and extra test period (07)

Nine candidates were built from the IS leaders. All are NQ long mean reversion, entering at
the 18:05 reopen.

| candidate | IS n | IS WR | OOS n | OOS WR | OOS exp. R | ^NDX 2000-10 WR |
|---|---|---|---|---|---|---|
| **C1: 3+ down closes, stop 2 ATR (selected: best IS lower bound)** | 114 | 80.7% | 91 | **73.6%** | +0.104 | 69.8% (149) |
| C2: any of {RSI2<10, IBS<0.2, 3 down closes, BB z<-1.5}, 2 ATR | 283 | 73.1% | 214 | 74.3% | +0.113 | 69.3% (355) |
| C3: 2 of those 4, 2 ATR | 152 | 78.3% | 106 | 70.8% | +0.059 | 71.0% (186) |
| C4: any of 4, 1.5 ATR | 387 | 72.9% | 285 | 70.9% | +0.062 | |
| C5: 2 of 4, 1.5 ATR | 180 | 74.4% | 129 | 69.0% | +0.034 | |
| C6: any of 4 + above 200-day SMA, 2 ATR | 219 | 73.1% | 158 | 74.1% | +0.110 | |
| C7: 2 of 4 + above 200-day SMA, 2 ATR | 107 | 80.4% | 71 | 67.6% | +0.013 | |
| C8: 2 of 4, entry 09:30 instead of 18:05 | 156 | 75.6% | 109 | 69.7% | +0.040 | |
| C9: 3 of 4, 2 ATR | 78 | 76.9% | 65 | 76.9% | +0.153 | |

The in-sample leaders (C1 and C7, about 80%) lose 7-13 points out of sample. The broader rules
(C2, C6) are more stable but lower, at about 74%. In 2000-2010, a period that includes two
bear markets, every version wins about 69-71%, compared with 67.5% for always-long.

## 5. Popular "90%" setups under a strict 0.5R bracket (08)

| setup | NQ WR | GC WR | expectancy |
|---|---|---|---|
| Gap fill: fade the 09:30 gap, target = prior close, stop = 2x gap (small gaps 0.1-0.2 ATR) | 67.3% | 60.6% | about 0 |
| Gap fill, gaps 0.35-0.6 ATR (flat at 16:00) | 39.0% | 24.5% | <= 0 |
| 15-minute opening-range breakout, stop = other side of the range | 61.7% | 59.8% | -0.07R / -0.10R |

## 6. Walk-forward model ceiling (09)

Hourly decision points, with test years 2014-2026. Hypothetical long and short brackets use
0.25, 0.5, 1 and 2 ATR stops. A gradient-boosting classifier with 29 causal features (multi-horizon
returns, session range and position, prior-day levels, realised and ATR volatility regime,
RSI, IBS, streaks, distance to moving averages, time of day, weekday) is retrained every 2
years on past data only, with a 10-day embargo.

Non-overlapping trades taken whenever the model predicted P(win) >= 0.9 realised:

| | stop 0.25 ATR | 0.5 ATR | 1 ATR | 2 ATR |
|---|---|---|---|---|
| NQ long | 73.9% (134) | 69.3% (368) | 67.5% (687) | 70.2% (459) |
| NQ short | 66.7% (24) | 70.5% (129) | 57.7% (274) | 60.2% (196) |
| GC long | 66.7% (6) | 66.0% (53) | 66.0% (188) | 72.7% (194) |
| GC short | 72.7% (44) | 67.5% (194) | 67.8% (289) | 62.6% (238) |

When the model claims 90% confidence, it is right only about 58-74% of the time. The
features contain no reliably identifiable pocket where a 0.5R bracket wins 90%.

## Conclusion

- A fixed 0.5R bracket on NQ or GC with a genuine 90% win rate was not found, and the evidence
  above suggests it is not attainable with information available before the trade.
- The most robust edge is short-term mean reversion in the Nasdaq after a string of down
  closes. It wins about 70-74% out of sample, roughly 3-7 points above break-even. The
  selected version (C1) is documented in the [README](../README.md) and
  [`strategy_results.md`](strategy_results.md).
- Gold showed no comparable short-term edge. Its high win rates come only from riding its
  trend with very wide stops.
