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
