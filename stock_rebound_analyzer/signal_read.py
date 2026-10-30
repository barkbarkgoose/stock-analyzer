"""The current-state read shown in the workbench and used by paper trading."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from .config import AnalysisConfig
from .labels import stop_price_for
from .model import predict_probability
from .rules import (
    SignalRule,
    bounce_room_left,
    evaluates,
    in_dip,
    trend_ok,
    is_candidate_bar,
    watch_checklist,
)
from .types import FeatureRow


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _waiting_for(
    row: FeatureRow,
    config: AnalysisConfig,
    watch: list[dict[str, Any]],
    buy: list[dict[str, Any]],
    rule: SignalRule | None,
) -> list[str]:
    if not row.episode_active:
        return [f"a dip of at least {config.dip_threshold_pct:g}% from the recent high"]
    if not bounce_room_left(row, config.max_runup_from_low_pct):
        return [
            "a fresh pullback — this bounce is already "
            f"{row.episode_recovery_pct:.2f}% off the low, past the "
            f"{config.max_runup_from_low_pct:.2f}% cutoff"
        ]
    waiting = [str(item["label"]) for item in watch if not item["ok"]]
    if rule is None:
        waiting.append("a buy rule with a net-positive track record on this stock (none yet)")
    else:
        waiting.extend(str(item["label"]) for item in buy if not item["ok"])
    return waiting or ["nothing — the buy rule is firing"]


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

    watch = watch_checklist(row, config)
    buy = recommended_rule.checklist(row) if recommended_rule else []
    if recommended_fire:
        state = "signal"
        detail = f"{recommended_rule.name} is firing on the latest bar."  # type: ignore[union-attr]
    elif (
        in_dip(row, config)
        and trend_ok(row, config)
        and bounce_room_left(row, config.max_runup_from_low_pct)
    ):
        state = "watching"
        if not recommended_rule:
            detail = "In a dip with bounce room left, but no buy rule has earned trust on this stock yet."
        elif not candidate:
            detail = "In a dip with bounce room left, but outside the trading window for this time of day."
        else:
            detail = "In a dip with bounce room left. Waiting for the buy rule to confirm the turn."
    elif row.episode_active and not bounce_room_left(row, config.max_runup_from_low_pct):
        state = "extended"
        detail = (
            "Still in the dip, but this bounce has already used up its typical room. "
            "Waiting for a pullback."
        )
    else:
        state = "no_setup"
        detail = "Not in a qualifying dip right now."

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
        "off_low_pct": row.episode_recovery_pct,
        "cutoff_pct": config.max_runup_from_low_pct,
        "cutoff_mode": config.runup_cutoff_mode,
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
        "recommended_rule_id": recommended_rule.id if recommended_rule else None,
        "recommended_rule_name": recommended_rule.name if recommended_rule else None,
        "watch_checklist": watch,
        "buy_checklist": buy,
        "probability": probability,
        "probability_fast": probability_fast,
        "levels": {
            "entry_estimate": entry_estimate,
            "target": target,
            "stop": stop,
            "target_pct": config.target_pct,
            "stop_pct": (1.0 - stop / entry_estimate) * 100.0 if entry_estimate else 0.0,
        },
        "waiting_for": _waiting_for(row, config, watch, buy, recommended_rule),
        "fake_rebound_risk": _fake_rebound_risk(row, probability),
    }


