"""Triple-barrier trade labelling.

Entry is always the *next* bar's open after a signal closes.  That removes the
most common backtest leak (buying at the same close that generated the signal).
If target and stop are both touched inside one bar we assume the stop was hit
first.  The result is a deliberately pessimistic, reproducible label.
"""

from __future__ import annotations

from .config import AnalysisConfig
from .types import TIMEFRAME_MINUTES, Bar, FeatureRow, TradeOutcome


def stop_price_for(
    entry_price: float, row: FeatureRow | None, config: AnalysisConfig
) -> float:
    if config.stop_mode == "episode_low" and row is not None and row.episode_low:
        candidate = row.episode_low * (1.0 - config.stop_buffer_pct / 100.0)
        floor = entry_price * (1.0 - config.min_stop_pct / 100.0)
        cap = entry_price * (1.0 - config.max_stop_pct / 100.0)
        return max(min(candidate, floor), cap)
    return entry_price * (1.0 - config.stop_pct / 100.0)


def label_entry(
    bars: list[Bar],
    signal_index: int,
    config: AnalysisConfig,
    row: FeatureRow | None = None,
    *,
    max_hold_bars: int | None = None,
) -> TradeOutcome | None:
    entry_index = signal_index + 1
    if entry_index >= len(bars):
        return None

    entry_bar = bars[entry_index]
    entry_price = entry_bar.open * (1.0 + config.entry_slippage_bps / 10_000.0)
    if entry_price <= 0:
        return None

    target = entry_price * (1.0 + config.target_pct / 100.0)
    stop = stop_price_for(entry_price, row, config)
    if stop <= 0 or stop >= entry_price:
        stop = entry_price * (1.0 - config.stop_pct / 100.0)

    hold_bars = max_hold_bars or config.max_hold_bars
    last_index = min(len(bars) - 1, entry_index + hold_bars - 1)
    max_high = entry_price
    min_low = entry_price
    exit_index = last_index
    exit_raw = bars[last_index].close
    exit_reason = "timeout"
    exit_price = exit_raw * (1.0 - config.exit_slippage_bps / 10_000.0)

    for j in range(entry_index, last_index + 1):
        bar = bars[j]
        max_high = max(max_high, bar.high)
        min_low = min(min_low, bar.low)

        if j > entry_index:
            # Opening gap beyond a barrier.  A stop gap is filled at the open
            # (worse); a target gap is modelled at the target (conservative).
            if bar.open <= stop:
                exit_index = j
                exit_raw = bar.open
                exit_reason = "stop"
                exit_price = exit_raw * (1.0 - config.exit_slippage_bps / 10_000.0)
                break
            if bar.open >= target:
                exit_index = j
                exit_raw = target
                exit_reason = "target"
                exit_price = exit_raw * (1.0 - config.exit_slippage_bps / 10_000.0)
                break

        hit_target = bar.high >= target
        hit_stop = bar.low <= stop
        if hit_target and hit_stop:
            # Same-bar ambiguity: assume the stop happened first.
            exit_index = j
            exit_raw = stop
            exit_reason = "stop"
            exit_price = exit_raw * (1.0 - config.exit_slippage_bps / 10_000.0)
            break
        if hit_stop:
            exit_index = j
            exit_raw = stop
            exit_reason = "stop"
            exit_price = exit_raw * (1.0 - config.exit_slippage_bps / 10_000.0)
            break
        if hit_target:
            exit_index = j
            exit_raw = target
            exit_reason = "target"
            exit_price = exit_raw * (1.0 - config.exit_slippage_bps / 10_000.0)
            break
    else:
        exit_reason = "end_of_data" if last_index < entry_index + hold_bars - 1 else "timeout"

    gross_return = (exit_price / entry_price - 1.0) * 100.0
    commission_pct = (config.commission_bps * 2.0) / 100.0
    net_return = gross_return - commission_pct
    holding_bars = exit_index - entry_index + 1
    minutes_per_bar = TIMEFRAME_MINUTES.get(config.timeframe)
    holding_trading_minutes = (
        holding_bars * minutes_per_bar
        if minutes_per_bar is not None
        else holding_bars * 390.0
    )
    holding_minutes = (bars[exit_index].ts - entry_bar.ts).total_seconds() / 60.0
    success = exit_reason == "target"
    if config.timeframe == "1d":
        fast_success = bool(success and holding_bars <= 1)
    else:
        fast_success = bool(
            success and holding_trading_minutes <= config.fast_horizon_minutes
        )

    return TradeOutcome(
        entry_index=entry_index,
        entry_ts=entry_bar.ts,
        entry_price=entry_price,
        exit_index=exit_index,
        exit_ts=bars[exit_index].ts,
        exit_price=exit_price,
        return_pct=gross_return,
        net_return_pct=net_return,
        mfe_pct=(max_high / entry_price - 1.0) * 100.0,
        mae_pct=(min_low / entry_price - 1.0) * 100.0,
        holding_bars=holding_bars,
        holding_minutes=holding_minutes,
        holding_trading_minutes=holding_trading_minutes,
        exit_reason=exit_reason,  # type: ignore[arg-type]
        success=success,
        fast_success=fast_success,
        target_price=target,
        stop_price=stop,
    )


def label_all(
    bars: list[Bar],
    rows: list[FeatureRow],
    config: AnalysisConfig,
) -> list[TradeOutcome | None]:
    """Label entry at the next open for every bar (rule independent)."""

    return [
        label_entry(bars, i, config, rows[i] if i < len(rows) else None)
        for i in range(len(bars))
    ]
