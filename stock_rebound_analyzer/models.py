from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class DipEvent:
    date: date
    dip_pct: float
    entry_price: float
    max_return_pct: float
    worst_drawdown_pct: float
    success: bool
    days_to_target: int | None


@dataclass(frozen=True)
class AnalysisReport:
    symbol: str
    bar_count: int
    dip_count: int
    success_count: int
    success_rate: float
    confidence_low: float
    confidence_high: float
    average_max_return_pct: float
    average_worst_drawdown_pct: float
    dip_events: list[DipEvent]
