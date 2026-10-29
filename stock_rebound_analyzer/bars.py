"""Bar normalisation and small time-series helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from .indicators import in_regular_session
from .types import Bar


def normalize_bars(
    bars: list[Bar],
    *,
    timeframe: str | None = None,
    regular_hours_only: bool = True,
) -> list[Bar]:
    """Sort, de-duplicate and lightly validate provider output.

    Duplicate timestamps are resolved by keeping the last occurrence (providers
    frequently return an overlapping bar when an incremental request is made).
    """

    target_tf = timeframe or (bars[0].timeframe if bars else "1d")
    by_ts: dict[datetime, Bar] = {}
    for bar in bars:
        if target_tf == "1d":
            ts = bar.ts.astimezone(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            ts = bar.ts.astimezone(timezone.utc)
        if regular_hours_only and target_tf != "1d" and not in_regular_session(
            Bar(
                symbol=bar.symbol,
                ts=ts,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                timeframe=bar.timeframe,
                source=bar.source,
            )
        ):
            continue
        by_ts[ts] = Bar(
            symbol=bar.symbol,
            ts=ts,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=max(0, int(bar.volume)),
            timeframe=target_tf,
            source=bar.source,
        )

    return [by_ts[key] for key in sorted(by_ts)]


def resample_daily(bars: list[Bar]) -> list[Bar]:
    """Aggregate intraday bars into daily bars (used for tests/demos)."""

    if not bars:
        return []
    from .indicators import session_date

    buckets: dict[object, list[Bar]] = {}
    for bar in bars:
        buckets.setdefault(session_date(bar), []).append(bar)

    out: list[Bar] = []
    for day in sorted(buckets):
        group = sorted(buckets[day], key=lambda b: b.ts)
        out.append(
            Bar(
                symbol=group[0].symbol,
                ts=datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
                open=group[0].open,
                high=max(b.high for b in group),
                low=min(b.low for b in group),
                close=group[-1].close,
                volume=sum(b.volume for b in group),
                timeframe="1d",
                source=group[0].source,
            )
        )
    return out


def slice_bars(
    bars: list[Bar], start: datetime | None = None, end: datetime | None = None
) -> list[Bar]:
    out = bars
    if start is not None:
        out = [b for b in out if b.ts >= start]
    if end is not None:
        out = [b for b in out if b.ts <= end]
    return out
