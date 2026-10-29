from __future__ import annotations

from datetime import datetime, timedelta, timezone

from stock_rebound_analyzer.bars import normalize_bars
from stock_rebound_analyzer.providers.synthetic import synthetic_bars
from stock_rebound_analyzer.types import Bar


def test_synthetic_history_is_stable_when_more_days_are_requested() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end1 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    end2 = datetime(2026, 4, 1, tzinfo=timezone.utc)
    daily1 = synthetic_bars("DEMO", "1d", start, end1)
    daily2 = synthetic_bars("DEMO", "1d", start, end2)
    overlap = [bar for bar in daily2 if bar.ts <= end1]
    assert [b.ts for b in daily1] == [b.ts for b in overlap]
    assert [b.close for b in daily1] == [b.close for b in overlap]


def test_normalize_bars_dedupes_and_sorts() -> None:
    ts = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    bars = [
        Bar("TEST", ts + timedelta(minutes=5), 101, 102, 100, 101.5, 100, "5m"),
        Bar("TEST", ts, 100, 101, 99, 100.5, 100, "5m"),
        Bar("TEST", ts + timedelta(minutes=5), 101, 103, 100, 102.5, 200, "5m"),
    ]
    out = normalize_bars(bars, timeframe="5m")
    assert len(out) == 2
    assert out[0].ts < out[1].ts
    assert out[1].close == 102.5
    assert out[1].volume == 200
