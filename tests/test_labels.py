from __future__ import annotations

from datetime import timedelta

from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.labels import label_entry
from stock_rebound_analyzer.types import Bar
from tests.conftest import session_ts


def bar(i: int, o: float, h: float, l: float, c: float, v: int = 1000, symbol: str = "TEST") -> Bar:
    return Bar(
        symbol=symbol,
        ts=session_ts("2026-01-05") + timedelta(minutes=5 * i),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        timeframe="5m",
        source="test",
    )


def cfg(**overrides) -> AnalysisConfig:
    base = dict(
        timeframe="5m",
        dip_threshold_pct=5.0,
        target_pct=1.0,
        stop_pct=2.0,
        max_hold_days=1.0,
        entry_slippage_bps=0,
        exit_slippage_bps=0,
        commission_bps=0,
    )
    base.update(overrides)
    return AnalysisConfig(**base)


def test_target_hit_on_next_bar() -> None:
    bars = [
        bar(0, 100, 100.5, 99.5, 100),
        bar(1, 100, 102.0, 99.9, 101.5),
    ]
    outcome = label_entry(bars, 0, cfg())
    assert outcome is not None
    assert outcome.success
    assert outcome.exit_reason == "target"
    assert outcome.entry_index == 1
    assert outcome.entry_price == 100
    assert abs(outcome.net_return_pct - 1.0) < 1e-9


def test_stop_hit() -> None:
    bars = [
        bar(0, 100, 100.5, 99.5, 100),
        bar(1, 100, 100.2, 97.5, 98.0),
    ]
    outcome = label_entry(bars, 0, cfg())
    assert outcome is not None
    assert not outcome.success
    assert outcome.exit_reason == "stop"
    assert abs(outcome.net_return_pct + 2.0) < 1e-9


def test_same_bar_target_and_stop_is_pessimistic() -> None:
    bars = [
        bar(0, 100, 100.5, 99.5, 100),
        bar(1, 100, 103.0, 97.0, 100.0),
    ]
    outcome = label_entry(bars, 0, cfg())
    assert outcome is not None
    assert outcome.exit_reason == "stop"
    assert not outcome.success


def test_entry_is_next_open_not_signal_close() -> None:
    bars = [
        bar(0, 100, 101, 99, 100),
        bar(1, 105, 105.5, 104.9, 105.2),
        bar(2, 105.2, 105.3, 105.0, 105.1),
    ]
    outcome = label_entry(bars, 0, cfg())
    assert outcome is not None
    assert outcome.entry_price == 105
    assert outcome.exit_reason in {"timeout", "end_of_data"}


def test_timeout_uses_last_close() -> None:
    bars = [
        bar(0, 100, 100.5, 99.5, 100),
        bar(1, 100, 100.4, 99.8, 100.2),
        bar(2, 100.2, 100.5, 99.9, 100.3),
    ]
    outcome = label_entry(bars, 0, cfg(max_hold_days=1.0))
    assert outcome is not None
    assert outcome.exit_reason in {"timeout", "end_of_data"}
    assert not outcome.success
