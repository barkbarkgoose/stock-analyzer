"""The current-state read shown in the workbench and used by paper trading."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from .config import AnalysisConfig
from .labels import stop_price_for
from .model import predict_probability
from .rules import SignalRule, evaluates, is_candidate_bar
from .types import FeatureRow


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _waiting_for(row: FeatureRow, config: AnalysisConfig) -> list[str]:
    if not row.episode_active:
        return [f"a >= {config.dip_threshold_pct:.1f}% dip episode"]
    if row.runup_from_low_pct > config.max_runup_from_low_pct:
        return ["a fresh pullback; the rebound is already extended"]
    waiting: list[str] = []
    if not row.higher_low:
        waiting.append("a confirmed higher low")
    if not row.close_above_prior_high:
        waiting.append("a close above the prior bar high")
    if row.ema9 is not None and not row.close_above_ema9:
        waiting.append("reclaim of the 9-EMA")
    if row.session_vwap is not None and not row.close_above_vwap:
        waiting.append("reclaim of session VWAP")
    if row.failed_bounces_1pct == 0:
        waiting.append("a failed first bounce or a structural break")
    return waiting or ["confirmation already present"]


def _fake_rebound_risk(row: FeatureRow, probability: float | None) -> dict[str, Any]:
    if not row.episode_active:
        return {
            "level": "n/a",
            "detail": "No active dip episode; fake-rebound risk is not meaningful right now.",
        }
    attempts = row.failed_bounces_1pct
    if attempts >= 2:
        level = "lower"
        detail = (
            "Two or more prior >=1% bounces failed. This is a later attempt with "
            "more evidence, but it still needs confirmation."
        )
    elif attempts == 1:
        level = "moderate"
        detail = "One prior >=1% bounce failed; the first fake-rebound risk is behind us."
    else:
        level = "elevated"
        detail = "This is the first bounce after the dip; fake rebounds are most common here."
    if probability is not None:
        if probability < 0.5:
            level = "high"
            detail = (
                f"Model probability is {probability:.0%}; the confirmation context is "
                "not strong enough yet."
            )
        else:
            detail += f" Model probability is {probability:.0%}."
    return {"level": level, "detail": detail}


def build_signal_read(
    rows: Sequence[FeatureRow],
    rules: Sequence[SignalRule],
    recommended_rule: SignalRule | None,
    model_spec: dict[str, Any] | None,
    fast_spec: dict[str, Any] | None,
    config: AnalysisConfig,
) -> dict[str, Any]:
    if not rows:
        return {"state": "no_data", "detail": "No bars available."}
    row = rows[-1]
    candidate = is_candidate_bar(row, config)
    fired = [rule for rule in rules if evaluates(row, rule, config)]
    recommended_fire = bool(
        recommended_rule and recommended_rule in fired
    )
    probability = (
        predict_probability(model_spec, row) if model_spec and candidate else None
    )
    probability_fast = (
        predict_probability(fast_spec, row) if fast_spec and candidate else None
    )

    entry_estimate = row.close * (1.0 + config.entry_slippage_bps / 10_000.0)
    stop = stop_price_for(entry_estimate, row, config)
    target = entry_estimate * (1.0 + config.target_pct / 100.0)

    if recommended_fire:
        state = "signal"
        detail = f"{recommended_rule.name} is firing on the latest bar."  # type: ignore[union-attr]
    elif candidate:
        state = "watching"
        detail = "A dip episode is active, but the confirmation has not triggered."
    else:
        state = "no_setup"
        detail = "No qualifying dip setup on the latest bar."

    return {
        "state": state,
        "detail": detail,
        "ts": _iso(row.ts),
        "price": row.close,
        "candidate": candidate,
        "episode_active": row.episode_active,
        "episode_depth_pct": row.episode_depth_pct,
        "episode_recovery_pct": row.episode_recovery_pct,
        "runup_from_low_pct": row.runup_from_low_pct,
        "bars_since_episode_low": row.bars_since_episode_low,
        "attempt_number": row.attempt_number,
        "failed_bounces": row.failed_bounces,
        "failed_bounces_1pct": row.failed_bounces_1pct,
        "higher_low": row.higher_low,
        "close_above_prior_high": row.close_above_prior_high,
        "close_above_ema9": row.close_above_ema9,
        "close_above_vwap": row.close_above_vwap,
        "rsi14": row.rsi14,
        "volume_ratio20": row.volume_ratio20,
        "daily_trend_score": row.daily_trend_score,
        "fired_rules": [
            {
                "id": rule.id,
                "name": rule.name,
                "family": rule.family,
                "baseline": rule.id == "dip_close",
            }
            for rule in fired
        ],
        "recommended_fire": recommended_fire,
        "probability": probability,
        "probability_fast": probability_fast,
        "levels": {
            "entry_estimate": entry_estimate,
            "target": target,
            "stop": stop,
            "target_pct": config.target_pct,
            "stop_pct": (1.0 - stop / entry_estimate) * 100.0 if entry_estimate else 0.0,
        },
        "waiting_for": _waiting_for(row, config),
        "fake_rebound_risk": _fake_rebound_risk(row, probability),
    }


