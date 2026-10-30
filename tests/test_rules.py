from __future__ import annotations

from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.rules import RULE_BY_ID, available_rules, evaluates
from stock_rebound_analyzer.types import FeatureRow
from datetime import datetime, timezone


def row(**overrides) -> FeatureRow:
    base = dict(
        index=10,
        ts=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        session=datetime(2026, 1, 5).date(),
        open=100,
        high=101,
        low=99,
        close=100.5,
        volume=1000,
        episode_active=True,
        episode_depth_pct=6.0,
        minutes_since_open=120,
        runup_from_low_pct=0.5,
        green_bar=True,
        close_above_prior_high=True,
        volume_ratio20=1.3,
        close_above_ema9=True,
        close_above_vwap=True,
        session_vwap=100.0,
        ema9=100.0,
        higher_low=True,
        close_above_prior_swing_high=True,
        failed_bounces_1pct=1,
        failed_bounces=1,
        attempt_number=2,
        rsi_cross_up_30=True,
    )
    base.update(overrides)
    return FeatureRow(**base)


def test_green_reclaim() -> None:
    config = AnalysisConfig(timeframe="5m", exclude_first_minutes=0)
    assert evaluates(row(), RULE_BY_ID["green_reclaim"], config)
    assert not evaluates(row(volume_ratio20=0.5), RULE_BY_ID["green_reclaim"], config)


def test_second_attempt_requires_failure_and_structure() -> None:
    config = AnalysisConfig(timeframe="5m", exclude_first_minutes=0)
    assert evaluates(row(), RULE_BY_ID["second_attempt"], config)
    assert not evaluates(row(failed_bounces=0, failed_bounces_1pct=0), RULE_BY_ID["second_attempt"], config)
    assert not evaluates(row(higher_low=False), RULE_BY_ID["second_attempt"], config)


def test_composite_balanced() -> None:
    config = AnalysisConfig(timeframe="5m", exclude_first_minutes=0)
    assert evaluates(row(), RULE_BY_ID["composite_balanced"], config)
    assert not evaluates(row(higher_low=False, close_above_prior_swing_high=False), RULE_BY_ID["composite_balanced"], config)


def test_daily_rules_exclude_vwap() -> None:
    config = AnalysisConfig(timeframe="1d")
    ids = {rule.id for rule in available_rules(config)}
    assert "vwap_reclaim" not in ids
    assert "composite_balanced" in ids


def test_checklist_is_exactly_the_trigger() -> None:
    from stock_rebound_analyzer.rules import RULES

    variants = [
        row(),
        row(higher_low=False),
        row(green_bar=False),
        row(volume_ratio20=0.9),
        row(new_low_recent=True),
        row(failed_bounces=0, failed_bounces_1pct=0),
        row(runup_from_low_pct=0.1),
        row(ema9_cross_up=True, vwap_cross_up=True, rsi_cross_up_30=False),
    ]
    for rule in RULES:
        for r in variants:
            checks = rule.checklist(r)
            assert all(item["ok"] for item in checks) == rule.evaluate(r)


def test_bounce_cutoff_uses_the_dip_low() -> None:
    config = AnalysisConfig(timeframe="5m", exclude_first_minutes=0, max_runup_from_low_pct=2.0)
    rule = RULE_BY_ID["green_reclaim"]
    assert evaluates(row(episode_recovery_pct=1.9), rule, config)
    # Far off the dip low: no bounce room left, even if the 2-day rolling
    # run-up looks small.
    assert not evaluates(row(episode_recovery_pct=2.1, runup_from_low_pct=0.5), rule, config)
