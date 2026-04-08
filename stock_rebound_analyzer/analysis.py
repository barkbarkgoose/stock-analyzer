from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .models import AnalysisReport, DailyBar, DipEvent


@dataclass
class _TrackedDipEvent:
    date: date
    dip_pct: float
    entry_price: float
    target_price: float
    observed_days: int = 0
    max_return_pct: float | None = None
    worst_drawdown_pct: float | None = None
    historical_success: bool = False
    historical_days_to_target: int | None = None


def _wilson_interval(
    successes: int, total: int, z: float = 1.96
) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0

    p = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denom
    margin = (z / denom) * math.sqrt((p * (1 - p) / total) + (z2 / (4 * total * total)))
    return max(0.0, center - margin), min(1.0, center + margin)


def _finalize_event(event: _TrackedDipEvent, rebound_window_days: int) -> DipEvent:
    return DipEvent(
        date=event.date,
        dip_pct=event.dip_pct,
        entry_price=event.entry_price,
        observed_days=event.observed_days,
        window_complete=event.observed_days >= rebound_window_days,
        max_return_pct=event.max_return_pct if event.max_return_pct is not None else 0.0,
        worst_drawdown_pct=(
            event.worst_drawdown_pct if event.worst_drawdown_pct is not None else 0.0
        ),
        historical_success=event.historical_success,
        historical_days_to_target=event.historical_days_to_target,
    )


def analyze_dip_rebounds(
    symbol: str,
    bars: list[DailyBar],
    dip_threshold_pct: float = 0.05,
    rebound_target_pct: float = 0.03,
    rebound_window_days: int = 5,
) -> AnalysisReport:
    if dip_threshold_pct <= 0:
        raise ValueError("dip_threshold_pct must be > 0")
    if rebound_target_pct <= 0:
        raise ValueError("rebound_target_pct must be > 0")
    if rebound_window_days <= 0:
        raise ValueError("rebound_window_days must be > 0")

    events: list[_TrackedDipEvent] = []
    active_events: list[_TrackedDipEvent] = []

    # Start at index 1 because we compare today's close vs previous close.
    for idx in range(1, len(bars)):
        current = bars[idx]
        next_active_events: list[_TrackedDipEvent] = []

        # Update prior dip setups strictly left-to-right as each new bar arrives.
        for event in active_events:
            event.observed_days += 1

            observed_return = (current.high - event.entry_price) / event.entry_price
            observed_drawdown = (current.low - event.entry_price) / event.entry_price

            if event.max_return_pct is None or observed_return > event.max_return_pct:
                event.max_return_pct = observed_return
            if (
                event.worst_drawdown_pct is None
                or observed_drawdown < event.worst_drawdown_pct
            ):
                event.worst_drawdown_pct = observed_drawdown

            if (
                not event.historical_success
                and current.high >= event.target_price
            ):
                event.historical_success = True
                event.historical_days_to_target = event.observed_days

            if event.observed_days < rebound_window_days:
                next_active_events.append(event)

        active_events = next_active_events

        previous_close = bars[idx - 1].close
        if previous_close <= 0:
            continue

        dip_pct = (previous_close - current.close) / previous_close
        if dip_pct < dip_threshold_pct:
            continue

        event = _TrackedDipEvent(
            date=current.date,
            dip_pct=dip_pct,
            entry_price=current.close,
            target_price=current.close * (1 + rebound_target_pct),
        )
        events.append(event)
        active_events.append(event)

    finalized_events = [_finalize_event(event, rebound_window_days) for event in events]

    dip_count = len(finalized_events)
    resolved_dip_count = sum(
        1
        for event in finalized_events
        if event.historical_success or event.window_complete
    )
    completed_window_count = sum(1 for event in finalized_events if event.window_complete)
    success_count = sum(1 for event in finalized_events if event.historical_success)
    success_rate = success_count / resolved_dip_count if resolved_dip_count else 0.0
    confidence_low, confidence_high = _wilson_interval(success_count, resolved_dip_count)

    avg_max_return = (
        sum(event.max_return_pct for event in finalized_events if event.window_complete)
        / completed_window_count
        if completed_window_count
        else 0.0
    )
    avg_worst_drawdown = (
        sum(
            event.worst_drawdown_pct
            for event in finalized_events
            if event.window_complete
        )
        / completed_window_count
        if completed_window_count
        else 0.0
    )

    return AnalysisReport(
        symbol=symbol,
        bar_count=len(bars),
        dip_count=dip_count,
        resolved_dip_count=resolved_dip_count,
        completed_window_count=completed_window_count,
        success_count=success_count,
        success_rate=success_rate,
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        average_max_return_pct=avg_max_return,
        average_worst_drawdown_pct=avg_worst_drawdown,
        dip_events=finalized_events,
    )
