"""Deterministic synthetic market data for offline demos and tests.

``SYNTH-UP`` / ``DEMO`` is an uptrending, volatile stock with a mix of clean and
fake rebounds.  ``SYNTH-FAKE`` deliberately produces many multi-leg dips,
``SYNTH-CLEAN`` produces cleaner V-shaped recoveries, ``SYNTH-CHOP`` is
sideways, ``SYNTH-DOWN`` is a downtrend and ``SYNTH-QUIET`` is a low-volatility
uptrend that should fail the volatility screen.

The generator is seeded by the symbol and always starts at the same epoch, so a
given historical date produces the same bars regardless of when it is requested.
That makes it suitable for unit tests as well as the demo UI.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from ..bars import resample_daily
from ..indicators import NY, session_date, session_minutes
from ..types import Bar
from .base import DataProvider, utc_now

EPOCH = date(2020, 1, 2)
BARS_PER_DAY = 78


@dataclass(frozen=True)
class _Profile:
    base_price: float
    daily_drift: float
    daily_vol: float
    base_volume: float
    dip_probability: float
    fake_probability: float
    gap_dip_probability: float
    dip_min: float
    dip_max: float


_PROFILES = {
    "SYNTH-UP": _Profile(50.0, 0.00085, 0.025, 30_000, 0.13, 0.30, 0.03, 5.0, 10.0),
    "DEMO": _Profile(50.0, 0.00085, 0.025, 30_000, 0.13, 0.30, 0.03, 5.0, 10.0),
    "SYNTH": _Profile(50.0, 0.00085, 0.025, 30_000, 0.13, 0.30, 0.03, 5.0, 10.0),
    "SYNTH-FAKE": _Profile(40.0, 0.00090, 0.029, 38_000, 0.24, 0.78, 0.05, 6.0, 12.0),
    "SYNTH-CLEAN": _Profile(60.0, 0.00095, 0.021, 24_000, 0.14, 0.08, 0.02, 5.0, 8.0),
    "SYNTH-CHOP": _Profile(80.0, 0.00003, 0.022, 20_000, 0.09, 0.40, 0.03, 5.0, 9.0),
    "SYNTH-DOWN": _Profile(100.0, -0.00045, 0.027, 26_000, 0.10, 0.40, 0.03, 5.0, 10.0),
    "SYNTH-QUIET": _Profile(120.0, 0.00060, 0.009, 12_000, 0.01, 0.10, 0.00, 5.0, 6.0),
}


def _profile_for(symbol: str) -> _Profile:
    key = symbol.upper().strip()
    if key in _PROFILES:
        return _PROFILES[key]
    # Any SYNTH-* name gets a deterministic profile from the name.
    if key.startswith("SYNTH"):
        return _PROFILES["SYNTH-UP"]
    return _PROFILES["SYNTH-UP"]


def _seed(symbol: str) -> int:
    digest = hashlib.sha256(symbol.upper().encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _weekdays(start: date, end: date):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def _session_timestamps(day: date) -> list[datetime]:
    # 09:30 ET through 15:55 ET in 5-minute steps.
    out: list[datetime] = []
    for minute in range(0, 390, 5):
        dt = datetime(
            day.year,
            day.month,
            day.day,
            9 + (30 + minute) // 60,
            (30 + minute) % 60,
            tzinfo=NY,
        )
        out.append(dt.astimezone(timezone.utc))
    return out


_CACHE: dict[str, tuple[date, list[Bar]]] = {}
_CACHE_ORDER: list[str] = []


def _ensure_series(symbol: str, through: date) -> list[Bar]:
    symbol = symbol.upper().strip()
    cached = _CACHE.get(symbol)
    if cached and cached[0] >= through:
        return cached[1]

    end = max(through, utc_now().date())
    # Generate a little beyond "today" so the cache is stable across requests.
    end = end + timedelta(days=10)
    rng = random.Random(_seed(symbol))
    profile = _profile_for(symbol)
    bars: list[Bar] = []
    price = profile.base_price
    ou_noise = 0.0
    trading_day = 0

    all_days = list(_weekdays(EPOCH, end))
    for day_index, day in enumerate(all_days):
        near_end = day_index >= len(all_days) - 20
        trend_log = math.log(profile.base_price) + profile.daily_drift * trading_day
        ou_noise = 0.95 * ou_noise + rng.gauss(0.0, profile.daily_vol * 0.40)
        target_close = math.exp(trend_log + ou_noise)

        gap = rng.gauss(0.0, profile.daily_vol * 0.28)
        if not near_end and rng.random() < profile.gap_dip_probability:
            gap -= rng.uniform(0.05, 0.085)
        session_open = max(0.5, price * math.exp(gap))

        bar_vol = profile.daily_vol / math.sqrt(BARS_PER_DAY) * 1.2
        cumulative = 0.0
        raw_logs: list[float] = []
        for _ in range(BARS_PER_DAY):
            cumulative += rng.gauss(0.0, bar_vol)
            raw_logs.append(cumulative)
        start_log = math.log(session_open)
        target_log = math.log(max(0.1, target_close))
        bridge = target_log - start_log - raw_logs[-1]
        closes = [
            math.exp(start_log + raw_logs[i] + bridge * (i + 1) / BARS_PER_DAY)
            for i in range(BARS_PER_DAY)
        ]

        # Inject a dip episode.  A fake version bounces, makes a lower low and
        # then recovers; this is exactly the pattern the signal research is
        # designed to avoid.
        volume_multiplier = [1.0] * BARS_PER_DAY
        if not near_end and rng.random() < profile.dip_probability:
            depth = rng.uniform(profile.dip_min, profile.dip_max) / 100.0
            start = rng.randint(6, 30)
            dip_len = rng.randint(8, 26)
            trough = min(BARS_PER_DAY - 2, start + dip_len)
            fake = rng.random() < profile.fake_probability
            factor = [1.0] * BARS_PER_DAY
            for i in range(start, trough + 1):
                progress = (i - start) / max(1, trough - start)
                factor[i] = 1.0 - depth * progress
            if fake:
                bounce_end = min(
                    BARS_PER_DAY - 2, trough + max(4, dip_len // 2)
                )
                for i in range(trough, bounce_end + 1):
                    progress = (i - trough) / max(1, bounce_end - trough)
                    factor[i] = 1.0 - depth + depth * 0.55 * progress
                second_trough = min(
                    BARS_PER_DAY - 2, bounce_end + max(4, dip_len // 2)
                )
                for i in range(bounce_end, second_trough + 1):
                    progress = (i - bounce_end) / max(1, second_trough - bounce_end)
                    factor[i] = (
                        1.0 - depth * 0.45 - depth * 0.90 * progress
                    )
                recovery_end = min(BARS_PER_DAY - 1, second_trough + 70)
                for i in range(second_trough, recovery_end + 1):
                    progress = (i - second_trough) / max(1, recovery_end - second_trough)
                    factor[i] = (
                        1.0 - depth * 1.35 + depth * 1.35 * min(1.0, progress)
                    )
                volume_window_end = second_trough
            else:
                recovery_end = min(
                    BARS_PER_DAY - 1, trough + rng.randint(10, 35)
                )
                for i in range(trough, recovery_end + 1):
                    progress = (i - trough) / max(1, recovery_end - trough)
                    factor[i] = 1.0 - depth + depth * min(1.0, progress)
                volume_window_end = recovery_end
            factor = [max(0.05, value) for value in factor]
            closes = [max(0.1, closes[i] * factor[i]) for i in range(BARS_PER_DAY)]
            for i in range(start, min(BARS_PER_DAY, volume_window_end + 5)):
                volume_multiplier[i] = rng.uniform(1.8, 3.4)
            for i in range(max(0, start - 3), start):
                volume_multiplier[i] = rng.uniform(1.2, 1.9)

        timestamps = _session_timestamps(day)
        previous_close = session_open
        for i in range(BARS_PER_DAY):
            close = closes[i]
            open_price = previous_close
            wick = abs(rng.gauss(0.0, 0.0007))
            high = max(open_price, close) * (1.0 + wick)
            low = min(open_price, close) * (1.0 - wick)
            volume = max(
                1,
                int(
                    profile.base_volume
                    * rng.lognormvariate(0.0, 0.25)
                    * volume_multiplier[i]
                ),
            )
            try:
                bars.append(
                    Bar(
                        symbol=symbol,
                        ts=timestamps[i],
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                        timeframe="5m",
                        source="synthetic",
                    )
                )
            except ValueError:
                pass
            previous_close = close

        price = closes[-1]
        trading_day += 1

    _CACHE[symbol] = (end, bars)
    if symbol in _CACHE_ORDER:
        _CACHE_ORDER.remove(symbol)
    _CACHE_ORDER.append(symbol)
    while len(_CACHE_ORDER) > 6:
        evict = _CACHE_ORDER.pop(0)
        _CACHE.pop(evict, None)
    return bars


def _resample_intraday(bars: list[Bar], minutes: int) -> list[Bar]:
    buckets: dict[tuple[date, int], list[Bar]] = {}
    for bar in bars:
        session = session_date(bar)
        bucket = session_minutes(bar) // minutes
        buckets.setdefault((session, bucket), []).append(bar)
    out: list[Bar] = []
    for key in sorted(buckets):
        group = sorted(buckets[key], key=lambda b: b.ts)
        out.append(
            Bar(
                symbol=group[0].symbol,
                ts=group[0].ts,
                open=group[0].open,
                high=max(b.high for b in group),
                low=min(b.low for b in group),
                close=group[-1].close,
                volume=sum(b.volume for b in group),
                timeframe=group[0].timeframe,
                source="synthetic",
            )
        )
    return out


def _split_to_one_minute(bars: list[Bar]) -> list[Bar]:
    out: list[Bar] = []
    for bar in bars:
        span = bar.close - bar.open
        for minute in range(5):
            open_price = bar.open + span * minute / 5.0
            close = bar.open + span * (minute + 1) / 5.0
            high = max(open_price, close) + (bar.high - max(bar.open, bar.close)) / 5.0
            low = min(open_price, close) - (min(bar.open, bar.close) - bar.low) / 5.0
            out.append(
                Bar(
                    symbol=bar.symbol,
                    ts=bar.ts + timedelta(minutes=minute),
                    open=open_price,
                    high=max(high, open_price, close),
                    low=min(low, open_price, close),
                    close=close,
                    volume=max(1, bar.volume // 5),
                    timeframe="1m",
                    source="synthetic",
                )
            )
    return out


def synthetic_bars(
    symbol: str, timeframe: str, start: datetime, end: datetime
) -> list[Bar]:
    series = _ensure_series(symbol, end.date())
    if timeframe == "1d":
        daily = resample_daily(series)
        return [bar for bar in daily if start <= bar.ts <= end]
    if timeframe == "1m":
        minute_bars = _split_to_one_minute(series)
        return [bar for bar in minute_bars if start <= bar.ts <= end]
    minutes = {"5m": 5, "15m": 15, "30m": 30, "1h": 60}.get(timeframe)
    if minutes is None:
        raise ValueError(f"Unsupported synthetic timeframe {timeframe}")
    source = series if timeframe == "5m" else _resample_intraday(series, minutes)
    return [
        Bar(
            symbol=bar.symbol,
            ts=bar.ts,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            timeframe=timeframe,
            source="synthetic",
        )
        for bar in source
        if start <= bar.ts <= end
    ]


class SyntheticProvider(DataProvider):
    name = "synthetic"

    def describe(self) -> dict[str, object]:
        return {
            "name": "synthetic",
            "note": (
                "Deterministic offline data. Try DEMO, SYNTH-UP, SYNTH-FAKE, "
                "SYNTH-CLEAN, SYNTH-CHOP, SYNTH-DOWN, SYNTH-QUIET."
            ),
        }

    def fetch_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return synthetic_bars(symbol, timeframe, start, end)


__all__ = ["SyntheticProvider", "synthetic_bars", "EPOCH"]
