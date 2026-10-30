from __future__ import annotations

from datetime import datetime, timedelta, timezone

from stock_rebound_analyzer.blind import (
    breakeven_hit_rate,
    prepare,
    run_blind,
    watch_bands,
)
from stock_rebound_analyzer.bounces import bounce_profile, resolve_cutoff
from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.daily import build_daily_contexts
from stock_rebound_analyzer.features import build_features
from stock_rebound_analyzer.indicators import session_date
from stock_rebound_analyzer.labels import label_all
from stock_rebound_analyzer.profile import build_profile
from stock_rebound_analyzer.providers.synthetic import synthetic_bars
from stock_rebound_analyzer.rules import available_rules
from stock_rebound_analyzer.types import EpisodeRecord

END = datetime(2026, 6, 30, tzinfo=timezone.utc)
CONFIG = AnalysisConfig(timeframe="5m", daily_history_days=700, intraday_history_days=45)


def _replay(intraday, daily, config=CONFIG):
    sessions = sorted({session_date(b) for b in intraday})
    contexts = build_daily_contexts(daily, intraday_sessions=sessions, include_current_day=False)
    series = build_features(intraday, config, daily_context=contexts, symbol="DEMO")
    prep = prepare(series.rows, available_rules(config), config)
    outcomes = label_all(intraday, series.rows, config)
    return run_blind(prep, outcomes, series.episodes, config), series


def test_blind_replay_never_uses_the_future() -> None:
    daily = synthetic_bars("DEMO", "1d", END - timedelta(days=700), END)
    intraday = synthetic_bars("DEMO", "5m", END - timedelta(days=45), END)
    full, _ = _replay(intraday, daily)

    cut = full.decisions[len(full.decisions) // 2]["session"]
    cut_ts = next(b.ts for b in intraday if session_date(b) == cut)
    truncated, _ = _replay([b for b in intraday if b.ts < cut_ts], daily)

    # Every decision made before the cut is identical with or without the
    # bars after it.
    early = [d for d in full.decisions if d["session"] < cut]
    assert early == truncated.decisions[: len(early)]
    # So is every trade that had closed before the cut.
    closed = lambda trades: [  # noqa: E731
        (t.signal_ts, t.rule_id, t.outcome.exit_ts)
        for t in trades
        if t.outcome.exit_ts < cut_ts and t.outcome.exit_reason != "end_of_data"
    ]
    assert closed(full.trades) == closed(truncated.trades)


def test_blind_replay_waits_for_warmup_and_sits_out_without_a_record() -> None:
    daily = synthetic_bars("DEMO", "1d", END - timedelta(days=700), END)
    intraday = synthetic_bars("DEMO", "5m", END - timedelta(days=45), END)
    config = AnalysisConfig(
        timeframe="5m", blind_warmup_sessions=5, min_trades_for_rule=10_000
    )
    result, series = _replay(intraday, daily, config)

    first_session = series.rows[0].session
    assert result.decisions
    assert result.decisions[0]["session"] > first_session
    assert all(d["rule_id"] is None for d in result.decisions)
    assert result.trades == []


def _episode(max_bounce: float, end_day: int) -> EpisodeRecord:
    ts = datetime(2026, 1, end_day, 15, tzinfo=timezone.utc)
    return EpisodeRecord(
        episode_id=end_day,
        start_ts=ts - timedelta(days=1),
        end_ts=ts,
        reference_high=100,
        low=94,
        low_ts=ts,
        depth_pct=6,
        failed_bounces=1,
        failed_bounces_1pct=1,
        recovered=False,
        duration_bars=50,
        max_bounce_pct=max_bounce,
        bounce_pcts=(1.2, max_bounce),
    )


def test_auto_cutoff_is_learned_from_finished_dips_only() -> None:
    config = AnalysisConfig(target_pct=1.0, max_runup_from_low_pct=3.0)
    episodes = [_episode(b, day) for b, day in [(2.0, 2), (3.0, 3), (4.0, 4), (5.0, 5)]]

    # Too few finished dips before Jan 4: fixed fallback.
    cutoff, source = resolve_cutoff(
        episodes, config, before=datetime(2026, 1, 4, tzinfo=timezone.utc)
    )
    assert (cutoff, source) == (3.0, "fallback")

    # All four: 25th percentile of the biggest bounces (2.75) minus the target.
    cutoff, source = resolve_cutoff(episodes, config)
    assert source == "auto"
    assert cutoff == 1.75

    fixed = AnalysisConfig(runup_cutoff_mode="fixed", max_runup_from_low_pct=2.5)
    assert resolve_cutoff(episodes, fixed) == (2.5, "fixed")


def test_bounce_profile_reach_table() -> None:
    config = AnalysisConfig(target_pct=1.5)
    episodes = [_episode(b, day) for b, day in [(1.0, 2), (2.0, 3), (3.0, 4), (4.0, 5)]]
    profile = bounce_profile(episodes, config)
    reach = {row["level_pct"]: row for row in profile["reach"]}
    assert reach[1.5]["episodes"] == 3
    assert reach[3.0]["episodes_pct"] == 0.5
    # Two legs per episode (a failed 1.2% bounce plus the final leg).
    assert profile["legs"] == 8
    assert "4 past dips" in profile["interpretation"]


def test_breakeven_hit_rate() -> None:
    config = AnalysisConfig(
        target_pct=1.0, stop_pct=2.0, entry_slippage_bps=0, exit_slippage_bps=0
    )
    assert abs(breakeven_hit_rate(config) - 2 / 3) < 1e-9
    wider = config.with_overrides(target_pct=2.0)
    assert abs(breakeven_hit_rate(wider) - 0.5) < 1e-9


def test_watch_bands_merge_and_split_on_cutoff() -> None:
    daily = synthetic_bars("DEMO", "1d", END - timedelta(days=700), END)
    intraday = synthetic_bars("DEMO", "5m", END - timedelta(days=45), END)
    sessions = sorted({session_date(b) for b in intraday})
    contexts = build_daily_contexts(daily, intraday_sessions=sessions, include_current_day=False)
    series = build_features(intraday, CONFIG, daily_context=contexts)
    rows = series.rows

    bands = watch_bands(rows, CONFIG, [3.0] * len(rows))
    assert bands
    assert {band["kind"] for band in bands} <= {"watch", "extended"}
    assert all(band["start"] <= band["end"] for band in bands)
    # A tighter cutoff can only shrink the time spent watching.
    tight = watch_bands(rows, CONFIG, [0.5] * len(rows))

    def watch_time(items):
        return sum(
            ((b["end"] - b["start"]) for b in items if b["kind"] == "watch"),
            timedelta(),
        )

    assert watch_time(tight) <= watch_time(bands)
    # No cutoff means the blind trader was not active yet: no bands.
    assert watch_bands(rows, CONFIG, [None] * len(rows)) == []


def test_profile_has_strategy_and_blind_sections() -> None:
    daily = synthetic_bars("DEMO", "1d", END - timedelta(days=700), END)
    intraday = synthetic_bars("DEMO", "5m", END - timedelta(days=45), END)
    profile = build_profile(
        symbol="DEMO", daily_bars=daily, intraday_bars=intraday, config=CONFIG
    )
    strategy = profile["strategy"]
    assert strategy["status"] in {"active", "sit_out"}
    assert strategy["watch"]["text"].startswith("Watch when DEMO")
    assert strategy["sell"]["target_pct"] == CONFIG.target_pct
    if strategy["status"] == "active":
        assert strategy["buy"]["rule_id"] == profile["recommended"]["rule_id"]
        assert strategy["buy"]["rule_id"] != "dip_close"

    blind = profile["blind"]
    assert blind["available"]
    targets = [row["target_pct"] for row in blind["ladder"]]
    assert targets == sorted(targets)
    assert sum(1 for row in blind["ladder"] if row["current"]) == 1
    assert profile["bounce_profile"]["cutoff_pct"] == profile["config"]["max_runup_from_low_pct"]
    assert "walk_forward" not in profile
    assert profile["watch_bands"]["hindsight"]
