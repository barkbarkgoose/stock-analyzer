from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from stock_rebound_analyzer.config import AnalysisConfig
from stock_rebound_analyzer.profile import build_profile
from stock_rebound_analyzer.providers.synthetic import synthetic_bars


def _data(end: datetime, daily_days: int = 700, intraday_days: int = 45):
    daily = synthetic_bars("DEMO", "1d", end - timedelta(days=daily_days), end)
    intraday = synthetic_bars("DEMO", "5m", end - timedelta(days=intraday_days), end)
    return daily, intraday


def test_profile_end_to_end() -> None:
    end = datetime(2026, 6, 30, tzinfo=timezone.utc)
    daily, intraday = _data(end)
    config = AnalysisConfig(
        timeframe="5m",
        daily_history_days=700,
        intraday_history_days=45,
    )
    profile = build_profile(
        symbol="DEMO",
        daily_bars=daily,
        intraday_bars=intraday,
        config=config,
        data_info={"daily_source": "synthetic", "intraday_source": "synthetic"},
    )

    assert profile["meta"]["symbol"] == "DEMO"
    assert profile["meta"]["mode"] == "5m"
    assert profile["meta"]["bars_analyzed"] > 100
    assert profile["qualification"]["status"] in {"qualified", "watch", "reject"}
    assert profile["rules"]
    assert profile["recommended"] is not None
    assert profile["recommended"]["stats"]["trades"] >= 0
    assert profile["episode_summary"]["count"] >= 0
    assert profile["signal_read"]["state"] in {"signal", "watching", "extended", "no_setup"}
    assert isinstance(profile["warnings"], list)

    # The model needs numpy/sklearn. It is part of the backend requirements.
    if profile["model"]["available"]:
        assert profile["model"]["features"]
        assert profile["model"]["spec"]["coefficients"]
        assert 0 <= profile["model"]["recommended_threshold"] <= 1


def test_profile_is_deterministic() -> None:
    end = datetime(2026, 6, 30, tzinfo=timezone.utc)
    daily, intraday = _data(end)
    config = AnalysisConfig(timeframe="5m", daily_history_days=700, intraday_history_days=45)
    first = build_profile(symbol="DEMO", daily_bars=daily, intraday_bars=intraday, config=config)
    second = build_profile(symbol="DEMO", daily_bars=daily, intraday_bars=intraday, config=config)
    assert first["meta"]["config_hash"] == second["meta"]["config_hash"]
    assert first["recommended"]["rule_id"] == second["recommended"]["rule_id"]
    assert [t["entry_ts"] for t in first["trades"]] == [t["entry_ts"] for t in second["trades"]]
    assert first["episode_summary"] == second["episode_summary"]


def test_daily_fallback_when_intraday_is_short() -> None:
    end = datetime(2026, 6, 30, tzinfo=timezone.utc)
    daily, intraday = _data(end, intraday_days=2)
    config = AnalysisConfig(timeframe="5m", daily_history_days=700, intraday_history_days=45)
    profile = build_profile(
        symbol="DEMO",
        daily_bars=daily,
        intraday_bars=intraday[:20],
        config=config,
    )
    assert profile["meta"]["mode"] == "1d"
    assert profile["data"]["fallback"] is True
    assert any("fell back to daily" in warning for warning in profile["warnings"])
    assert all(rule["rule_id"] != "vwap_reclaim" for rule in profile["rules"])


def test_missing_data_is_graceful() -> None:
    profile = build_profile(symbol="NOPE", daily_bars=[], intraday_bars=[])
    assert profile["meta"]["error"] == "no_data"
    assert profile["recommended"] is None
    assert profile["warnings"]
