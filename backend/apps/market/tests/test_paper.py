from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.market.models import PaperTrade, Security
from apps.market.services.paper import (
    close_trade_manual,
    evaluate_open_trade,
    paper_stats,
)
from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.types import Bar


def _bar(ts: datetime, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(
        symbol="TEST",
        ts=ts,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1000,
        timeframe="5m",
        source="test",
    )


@pytest.mark.django_db
def test_evaluate_target_stop_and_timeout() -> None:
    security = Security.objects.create(symbol="TEST")
    entry_ts = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)
    trade = PaperTrade.objects.create(
        security=security,
        status="open",
        rule_id="composite_balanced",
        entry_ts=entry_ts,
        entry_price=100.0,
        notional=10_000.0,
        qty=100.0,
        target_price=101.0,
        stop_price=98.0,
    )
    config = AnalysisConfig(timeframe="5m", max_hold_days=1.0, exit_slippage_bps=0)

    target_bar = _bar(entry_ts + timedelta(minutes=5), 100, 101.5, 99.8, 101.4)
    target_exit = evaluate_open_trade(trade, [target_bar], config)
    assert target_exit is not None
    assert target_exit["exit_reason"] == "target"
    assert target_exit["exit_price"] == 101.0

    stop_bar = _bar(entry_ts + timedelta(minutes=5), 100, 100.2, 97.0, 97.5)
    stop_exit = evaluate_open_trade(trade, [stop_bar], config)
    assert stop_exit is not None
    assert stop_exit["exit_reason"] == "stop"
    assert stop_exit["exit_price"] == 98.0

    ambiguous = _bar(entry_ts + timedelta(minutes=5), 100, 102.0, 97.0, 100.0)
    ambiguous_exit = evaluate_open_trade(trade, [ambiguous], config)
    assert ambiguous_exit is not None
    assert ambiguous_exit["exit_reason"] == "stop"

    timeout_config = AnalysisConfig(timeframe="5m", max_hold_days=0.02, exit_slippage_bps=0)
    flat = [
        _bar(entry_ts + timedelta(minutes=5), 100, 100.4, 99.6, 100.1),
        _bar(entry_ts + timedelta(minutes=10), 100.1, 100.5, 99.7, 100.2),
    ]
    timeout_exit = evaluate_open_trade(trade, flat, timeout_config)
    assert timeout_exit is not None
    assert timeout_exit["exit_reason"] == "timeout"


@pytest.mark.django_db
def test_manual_close_and_stats() -> None:
    security = Security.objects.create(symbol="TEST2")
    trade = PaperTrade.objects.create(
        security=security,
        status="open",
        rule_id="rsi_reclaim",
        entry_ts=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        entry_price=100.0,
        notional=10_000.0,
        qty=100.0,
        target_price=101.0,
        stop_price=98.0,
    )
    closed = close_trade_manual(trade, 100.5)
    assert closed.status == "closed"
    assert closed.exit_reason == "manual"
    assert closed.return_pct == pytest.approx(0.5)
    assert closed.pnl == pytest.approx(50.0)
    stats = paper_stats()
    assert stats["closed_trades"] == 1
    assert stats["wins"] == 1
    assert stats["win_rate"] == 1.0
    assert stats["total_pnl"] == pytest.approx(50.0)
