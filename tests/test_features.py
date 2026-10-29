from __future__ import annotations

from datetime import timedelta

from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.features import build_features
from stock_rebound_analyzer.rules import is_candidate_bar
from stock_rebound_analyzer.types import Bar
from tests.conftest import session_ts


def make_series(closes: list[float], volumes: list[int] | None = None) -> list[Bar]:
    bars: list[Bar] = []
    for i, close in enumerate(closes):
        prev = closes[i - 1] if i else close
        open_price = prev
        high = max(open_price, close) * 1.001
        low = min(open_price, close) * 0.999
        bars.append(
            Bar(
                symbol="TEST",
                ts=session_ts("2026-01-05") + timedelta(minutes=5 * i),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volumes[i] if volumes else 1000,
                timeframe="5m",
                source="test",
            )
        )
    return bars


def test_multi_leg_dip_stays_one_episode_and_counts_failed_bounces() -> None:
    # 100 -> 94 (dip), bounce to 96, lower low to 90, then recover.
    closes = [100] * 5 + [99, 98, 97, 96, 95, 94] + [94.5, 95, 95.5, 96, 96.2, 95.8] + [95, 94, 93, 92, 91, 90] + [91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102]
    bars = make_series(closes)
    config = AnalysisConfig(timeframe="5m", dip_threshold_pct=5.0, swing_pivot_bars=2)
    series = build_features(bars, config)
    rows = series.rows
    # Find the second trough row (close 90).
    trough_index = closes.index(90)
    row = rows[trough_index]
    assert row.episode_active
    assert row.episode_depth_pct >= 9.0
    assert row.failed_bounces >= 1
    assert row.failed_bounces_1pct >= 1
    assert row.attempt_number >= 2
    assert len(series.episodes) == 1

    # After the recovery, the episode should have ended.
    final = rows[-1]
    assert not final.episode_active
    # And the feature rows are causal: truncating the future does not change
    # the row at the trough.
    truncated = build_features(bars[: trough_index + 1], config)
    assert truncated.rows[trough_index].episode_depth_pct == row.episode_depth_pct
    assert truncated.rows[trough_index].attempt_number == row.attempt_number


def test_candidate_gate_respects_time_and_runup() -> None:
    closes = [100] * 5 + [99, 98, 97, 96, 95, 94] + [95, 96, 97]
    bars = make_series(closes)
    config = AnalysisConfig(timeframe="5m", dip_threshold_pct=5.0, exclude_first_minutes=0)
    rows = build_features(bars, config).rows
    dip_row = rows[10]
    assert is_candidate_bar(dip_row, config)
    # A run-up beyond the cap is no longer a candidate.
    high_runup = rows[13]
    strict = config.with_overrides(max_runup_from_low_pct=0.1)
    assert not is_candidate_bar(high_runup, strict)


def test_episodes_require_threshold() -> None:
    closes = [100, 100.2, 100.1, 100.3, 100.2, 100.4]
    bars = make_series(closes)
    series = build_features(bars, AnalysisConfig(timeframe="5m", dip_threshold_pct=5.0))
    assert series.episodes == []
    assert not any(row.episode_active for row in series.rows)
