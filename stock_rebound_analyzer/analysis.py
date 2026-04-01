from __future__ import annotations

import math

from .models import AnalysisReport, DailyBar, DipEvent


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0

    p = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denom
    margin = (z / denom) * math.sqrt((p * (1 - p) / total) + (z2 / (4 * total * total)))
    return max(0.0, center - margin), min(1.0, center + margin)


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

    events: list[DipEvent] = []

    # Start at index 1 because we compare today's close vs previous close.
    for idx in range(1, len(bars)):
        previous_close = bars[idx - 1].close
        current = bars[idx]
        if previous_close <= 0:
            continue

        dip_pct = (previous_close - current.close) / previous_close
        if dip_pct < dip_threshold_pct:
            continue

        lookahead = bars[idx + 1 : idx + 1 + rebound_window_days]
        if len(lookahead) < rebound_window_days:
            # Skip partial windows to keep event evaluation consistent.
            continue

        entry_price = current.close
        max_high = max(bar.high for bar in lookahead)
        min_low = min(bar.low for bar in lookahead)

        max_return_pct = (max_high - entry_price) / entry_price
        worst_drawdown_pct = (min_low - entry_price) / entry_price

        success = max_return_pct >= rebound_target_pct
        target_price = entry_price * (1 + rebound_target_pct)
        days_to_target = None
        if success:
            for offset, bar in enumerate(lookahead, start=1):
                if bar.high >= target_price:
                    days_to_target = offset
                    break

        events.append(
            DipEvent(
                date=current.date,
                dip_pct=dip_pct,
                entry_price=entry_price,
                max_return_pct=max_return_pct,
                worst_drawdown_pct=worst_drawdown_pct,
                success=success,
                days_to_target=days_to_target,
            )
        )

    dip_count = len(events)
    success_count = sum(1 for event in events if event.success)
    success_rate = success_count / dip_count if dip_count else 0.0
    confidence_low, confidence_high = _wilson_interval(success_count, dip_count)

    avg_max_return = sum(event.max_return_pct for event in events) / dip_count if dip_count else 0.0
    avg_worst_drawdown = sum(event.worst_drawdown_pct for event in events) / dip_count if dip_count else 0.0

    return AnalysisReport(
        symbol=symbol,
        bar_count=len(bars),
        dip_count=dip_count,
        success_count=success_count,
        success_rate=success_rate,
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        average_max_return_pct=avg_max_return,
        average_worst_drawdown_pct=avg_worst_drawdown,
        dip_events=events,
    )
