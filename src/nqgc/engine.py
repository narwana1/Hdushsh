"""Fixed-bracket trade simulator on OHLC bars (minute or daily).

Every trade is a market entry at the OPEN of ``entry_idx`` with an OCO bracket:
stop at ``S`` points against the fill and target at ``rr * S`` points in favour.

Fill rules are deliberately pessimistic:
  * entry and stop exits pay ``slip`` ticks of slippage;
  * a target (resting limit) only fills if price trades *through* it by
    ``through`` ticks; if a bar opens beyond the target we still only get the
    target price (a real limit would get the better open);
  * a bar that opens beyond the stop fills at that open (minus slippage);
  * if one bar touches both stop and target we cannot know the order, so the
    trade is booked as a loss (and counted in ``ambiguous``);
  * the entry bar itself is checked too (its high/low print after the open).
Optional time exit: at the CLOSE of ``last_idx`` (market, with slippage).
"""
from __future__ import annotations

from dataclasses import dataclass

import numba as nb
import numpy as np
import pandas as pd

TARGET, STOP, TIME, OPEN_AT_END = 1, -1, 0, 9


@dataclass(frozen=True)
class Instrument:
    name: str
    tick: float  # minimum price increment
    point_value: float  # USD per 1.0 price move per contract
    commission_rt: float  # USD per contract round turn, incl. exchange/clearing/NFA fees


# Full-size contracts; micro contracts (MNQ/MGC) have 1/10 the point value and
# a proportionally larger commission in R terms, see report.
NQ = Instrument("NQ", 0.25, 20.0, 5.0)
GC = Instrument("GC", 0.10, 100.0, 5.0)


@dataclass(frozen=True)
class Fills:
    slip_ticks: float = 1.0  # market entry, stop and time exits
    through_ticks: float = 1.0  # target limit requires trade-through


@nb.njit(cache=True)
def _simulate(o, h, l, c, entry_idx, direction, stop_dist, last_idx, rr, slip, through):
    n = entry_idx.shape[0]
    nbar = o.shape[0]
    exit_idx = np.full(n, -1, np.int64)
    entry_px = np.zeros(n)
    exit_px = np.zeros(n)
    outcome = np.zeros(n, np.int8)
    ambiguous = np.zeros(n, np.bool_)
    for k in range(n):
        i = entry_idx[k]
        d = direction[k]
        s = stop_dist[k]
        e = o[i] + d * slip
        stop = e - d * s
        tgt = e + d * rr * s
        end = last_idx[k] if last_idx[k] >= 0 else nbar - 1
        if end > nbar - 1:
            end = nbar - 1
        entry_px[k] = e
        done = False
        for j in range(i, end + 1):
            if j > i:
                # gap through a level at the open of a later bar
                if (d == 1 and o[j] <= stop) or (d == -1 and o[j] >= stop):
                    exit_idx[k] = j
                    exit_px[k] = o[j] - d * slip
                    outcome[k] = STOP
                    done = True
                    break
                if (d == 1 and o[j] >= tgt + through) or (d == -1 and o[j] <= tgt - through):
                    exit_idx[k] = j
                    exit_px[k] = tgt
                    outcome[k] = TARGET
                    done = True
                    break
            if d == 1:
                hit_s = l[j] <= stop
                hit_t = h[j] >= tgt + through
            else:
                hit_s = h[j] >= stop
                hit_t = l[j] <= tgt - through
            if hit_s:
                if hit_t:
                    ambiguous[k] = True
                exit_idx[k] = j
                exit_px[k] = stop - d * slip
                outcome[k] = STOP
                done = True
                break
            if hit_t:
                exit_idx[k] = j
                exit_px[k] = tgt
                outcome[k] = TARGET
                done = True
                break
        if not done:
            exit_idx[k] = end
            exit_px[k] = c[end] - d * slip
            outcome[k] = TIME if last_idx[k] >= 0 and last_idx[k] <= nbar - 1 else OPEN_AT_END
    return exit_idx, entry_px, exit_px, outcome, ambiguous


def simulate(
    bars: pd.DataFrame,
    entry_idx: np.ndarray,
    direction: np.ndarray,
    stop_dist: np.ndarray,
    inst: Instrument,
    rr: float = 0.5,
    last_idx: np.ndarray | None = None,
    fills: Fills = Fills(),
) -> pd.DataFrame:
    """Simulate bracket trades. ``bars`` must have open/high/low/close and a DatetimeIndex.

    ``entry_idx`` are integer positions into ``bars`` (entry at that bar's OPEN).
    Signals must be computed from data that ended *before* that open.
    Trades are simulated independently; use :func:`no_overlap` to enforce one position at a time.
    """
    entry_idx = np.asarray(entry_idx, np.int64)
    n = len(entry_idx)
    direction = np.asarray(direction, np.int64)
    stop_dist = np.asarray(stop_dist, np.float64)
    if last_idx is None:
        last_idx = np.full(n, -1, np.int64)
    last_idx = np.asarray(last_idx, np.int64)
    if n and (stop_dist <= 0).any():
        raise ValueError("stop distance must be positive")
    if n and ((entry_idx < 0) | (entry_idx >= len(bars))).any():
        raise ValueError("entry index out of range")
    o, h, l, c = (bars[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    xi, epx, xpx, out, amb = _simulate(
        o, h, l, c, entry_idx, direction, stop_dist, last_idx, float(rr),
        fills.slip_ticks * inst.tick, fills.through_ticks * inst.tick,
    )
    idx = bars.index
    comm_pts = inst.commission_rt / inst.point_value
    pnl_pts = direction * (xpx - epx) - comm_pts
    return pd.DataFrame(
        {
            "entry_time": idx[entry_idx],
            "exit_time": idx[xi],
            "entry_idx": entry_idx,
            "exit_idx": xi,
            "dir": direction,
            "entry": epx,
            "exit": xpx,
            "stop_dist": stop_dist,
            "outcome": out,
            "ambiguous": amb,
            "pnl_pts": pnl_pts,
            "pnl_usd": pnl_pts * inst.point_value,
            "R": pnl_pts / stop_dist,
        }
    )


def no_overlap(trades: pd.DataFrame) -> pd.DataFrame:
    """Keep trades in time order, skipping any that start before the previous one exited."""
    if trades.empty:
        return trades
    t = trades.sort_values("entry_idx", kind="stable")
    keep = np.zeros(len(t), bool)
    last_exit = -1
    for n, (ei, xi) in enumerate(zip(t["entry_idx"].to_numpy(), t["exit_idx"].to_numpy())):
        if ei > last_exit:
            keep[n] = True
            last_exit = xi
    return t[keep]
