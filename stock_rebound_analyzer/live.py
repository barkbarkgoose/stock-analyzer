"""Lightweight current-state evaluation for watchlists and paper trading."""

from __future__ import annotations

from datetime import date
from typing import Any

from .bars import normalize_bars
from .config import AnalysisConfig
from .daily import build_daily_contexts
from .features import build_features
from .indicators import session_date
from .rules import RULE_BY_ID, available_rules
from .signal_read import build_signal_read
from .types import Bar


def build_live_read(
    *,
    symbol: str,
    daily_bars: list[Bar],
    bars: list[Bar],
    config: AnalysisConfig,
    model_spec: dict[str, Any] | None = None,
    fast_spec: dict[str, Any] | None = None,
    recommended_rule_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate the latest bar without rebuilding the full profile.

    The caller should pass enough intraday history to cover the active dip
    episode (15-20 sessions is plenty for a 5m timeframe).
    """

    daily_bars = normalize_bars(daily_bars, timeframe="1d")
    bars = normalize_bars(bars, timeframe=config.timeframe)
    if not bars:
        return {
            "signal_read": {"state": "no_data", "detail": "No bars available."},
            "mode": config.timeframe,
        }

    mode = config.timeframe
    if mode == "1d":
        contexts = build_daily_contexts(daily_bars, include_current_day=True)
        analysis_bars = daily_bars if daily_bars else bars
    else:
        sessions: list[date] = sorted({session_date(bar) for bar in bars})
        contexts = build_daily_contexts(
            daily_bars, intraday_sessions=sessions, include_current_day=False
        )
        analysis_bars = bars

    series = build_features(
        analysis_bars, config, daily_context=contexts, symbol=symbol
    )
    rules = available_rules(config)
    # No fallback rule: if the profile found no rule worth trusting, the live
    # read can still say "watching", but it never says "signal".
    recommended = RULE_BY_ID.get(recommended_rule_id) if recommended_rule_id else None
    if recommended is not None and recommended not in rules:
        recommended = None
    read = build_signal_read(
        series.rows,
        rules,
        recommended,
        model_spec,
        fast_spec,
        config,
    )
    read["recommended_rule_id"] = recommended.id if recommended else None
    return {
        "signal_read": read,
        "mode": mode,
        "rows": len(series.rows),
        "episodes": len(series.episodes),
        "last_ts": series.rows[-1].ts.isoformat() if series.rows else None,
    }


__all__ = ["build_live_read"]
