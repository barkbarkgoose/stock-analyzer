"""Causal technical indicators used by the feature builder.

All functions return lists aligned with the input.  Values that are not yet
available (warm-up) are ``None``.  No function looks into the future: the value
at index ``i`` is derived only from inputs ``0..i``.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, deque
from datetime import date
from zoneinfo import ZoneInfo

from .types import Bar, SESSION_MINUTES, SESSION_OPEN_MINUTES

NY = ZoneInfo("America/New_York")


def sma(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= window:
            running -= values[i - window]
        if i >= window - 1:
            out[i] = running / window
    return out


def ema(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    out: list[float | None] = [None] * len(values)
    if len(values) < window:
        return out
    seed = sum(values[:window]) / window
    out[window - 1] = seed
    alpha = 2.0 / (window + 1.0)
    prev = seed
    for i in range(window, len(values)):
        prev = (values[i] - prev) * alpha + prev
        out[i] = prev
    return out


def rsi(values: list[float], window: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= window:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, window + 1):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change

    avg_gain = gains / window
    avg_loss = losses / window
    out[window] = _rsi_value(avg_gain, avg_loss)

    for i in range(window + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = ((avg_gain * (window - 1)) + gain) / window
        avg_loss = ((avg_loss * (window - 1)) + loss) / window
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def true_ranges(bars: list[Bar]) -> list[float]:
    out: list[float] = []
    prev_close: float | None = None
    for bar in bars:
        if prev_close is None:
            out.append(bar.high - bar.low)
        else:
            out.append(
                max(
                    bar.high - bar.low,
                    abs(bar.high - prev_close),
                    abs(bar.low - prev_close),
                )
            )
        prev_close = bar.close
    return out


def atr(bars: list[Bar], window: int = 14) -> list[float | None]:
    tr = true_ranges(bars)
    out: list[float | None] = [None] * len(tr)
    if len(tr) < window:
        return out
    seed = sum(tr[:window]) / window
    out[window - 1] = seed
    prev = seed
    for i in range(window, len(tr)):
        prev = ((prev * (window - 1)) + tr[i]) / window
        out[i] = prev
    return out


def rolling_extreme(
    values: list[float], window: int, *, is_max: bool
) -> tuple[list[float | None], list[int | None]]:
    """Rolling max/min for windows ending at each index (inclusive)."""

    if window <= 0:
        raise ValueError("window must be positive")
    out: list[float | None] = [None] * len(values)
    idx_out: list[int | None] = [None] * len(values)
    dq: deque[int] = deque()

    for i, value in enumerate(values):
        while dq and (
            (values[dq[-1]] <= value) if is_max else (values[dq[-1]] >= value)
        ):
            dq.pop()
        dq.append(i)
        while dq and dq[0] <= i - window:
            dq.popleft()
        if i >= window - 1 and dq:
            best = dq[0]
            out[i] = values[best]
            idx_out[i] = best
    return out, idx_out


def rolling_mean(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= window:
            running -= values[i - window]
        if i >= window - 1:
            out[i] = running / window
    return out


def rolling_std(values: list[float], window: int) -> list[float | None]:
    if window <= 1:
        raise ValueError("window must be >= 2")
    out: list[float | None] = [None] * len(values)
    sum_x = 0.0
    sum_x2 = 0.0
    for i, value in enumerate(values):
        sum_x += value
        sum_x2 += value * value
        if i >= window:
            old = values[i - window]
            sum_x -= old
            sum_x2 -= old * old
        if i >= window - 1:
            variance = max(0.0, (sum_x2 - (sum_x * sum_x) / window) / (window - 1))
            out[i] = math.sqrt(variance)
    return out


def pct_change(values: list[float], periods: int = 1) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(periods, len(values)):
        base = values[i - periods]
        if base > 0:
            out[i] = (values[i] / base - 1.0) * 100.0
    return out


def confirmed_swings(
    bars: list[Bar], k: int
) -> tuple[list[float | None], list[float | None], list[float | None], list[float | None]]:
    """Return last/previous confirmed swing lows and highs per bar.

    A pivot at index ``j`` is only known at ``j + k`` (the right-hand bars are
    required for confirmation).  For feature row ``i`` we only expose pivots
    confirmed at or before ``i``, so the values are causally valid.
    """

    n = len(bars)
    last_low: list[float | None] = [None] * n
    prev_low: list[float | None] = [None] * n
    last_high: list[float | None] = [None] * n
    prev_high: list[float | None] = [None] * n

    low_events: list[tuple[int, float]] = []
    high_events: list[tuple[int, float]] = []

    for j in range(k, n - k):
        left_lows = [bars[x].low for x in range(j - k, j)]
        right_lows = [bars[x].low for x in range(j + 1, j + k + 1)]
        left_highs = [bars[x].high for x in range(j - k, j)]
        right_highs = [bars[x].high for x in range(j + 1, j + k + 1)]
        if bars[j].low < min(left_lows) and bars[j].low < min(right_lows):
            low_events.append((j + k, bars[j].low))
        if bars[j].high > max(left_highs) and bars[j].high > max(right_highs):
            high_events.append((j + k, bars[j].high))

    low_ptr = 0
    high_ptr = 0
    current_low: float | None = None
    current_prev_low: float | None = None
    current_high: float | None = None
    current_prev_high: float | None = None

    # Events are already sorted by confirmation index.  At a confirmation bar
    # we first expose the pivot value, then move the previous value back.
    for i in range(n):
        while low_ptr < len(low_events) and low_events[low_ptr][0] <= i:
            current_prev_low = current_low
            current_low = low_events[low_ptr][1]
            low_ptr += 1
        while high_ptr < len(high_events) and high_events[high_ptr][0] <= i:
            current_prev_high = current_high
            current_high = high_events[high_ptr][1]
            high_ptr += 1
        last_low[i] = current_low
        prev_low[i] = current_prev_low
        last_high[i] = current_high
        prev_high[i] = current_prev_high

    return last_low, prev_low, last_high, prev_high


def session_date(bar: Bar) -> date:
    if bar.timeframe == "1d":
        return bar.ts.date()
    return bar.ts.astimezone(NY).date()


def session_minutes(bar: Bar) -> int:
    """Minutes from the 09:30 regular open (clamped to the session)."""
    if bar.timeframe == "1d":
        return 0
    local = bar.ts.astimezone(NY)
    minutes = local.hour * 60 + local.minute - SESSION_OPEN_MINUTES
    return max(0, min(SESSION_MINUTES, minutes))


def session_progress(bar: Bar) -> float:
    if bar.timeframe == "1d":
        return 0.0
    return max(0.0, min(1.0, session_minutes(bar) / SESSION_MINUTES))


def in_regular_session(bar: Bar) -> bool:
    if bar.timeframe == "1d":
        return True
    local = bar.ts.astimezone(NY)
    minutes = local.hour * 60 + local.minute
    return SESSION_OPEN_MINUTES <= minutes < SESSION_OPEN_MINUTES + SESSION_MINUTES


def bars_per_session(bars: list[Bar]) -> float:
    """Median number of bars in a session, used for day-based barriers."""
    if not bars:
        return 1.0
    if bars[0].timeframe == "1d":
        return 1.0
    counts = Counter(session_date(bar) for bar in bars)
    if not counts:
        return 1.0
    return float(statistics.median(counts.values()))


def ns_until_close(bar: Bar) -> int:
    """Rough trading minutes remaining in the session (for time-of-day rules)."""
    if bar.timeframe == "1d":
        return 0
    return max(0, SESSION_MINUTES - session_minutes(bar))


def linear_slope(values: list[float]) -> float:
    """Least-squares slope per step; useful for short-term bounce quality."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    den = sum((i - mean_x) ** 2 for i in range(n))
    return num / den if den else 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


__all__ = [
    "NY",
    "atr",
    "bars_per_session",
    "clamp",
    "confirmed_swings",
    "ema",
    "in_regular_session",
    "linear_slope",
    "ns_until_close",
    "pct_change",
    "rolling_extreme",
    "rolling_mean",
    "rolling_std",
    "rsi",
    "session_date",
    "session_minutes",
    "session_progress",
    "sma",
    "true_ranges",
]
