from __future__ import annotations


import pytest
from rest_framework.test import APIClient

from apps.market.models import Bar, FetchLog, PaperTrade, ScreenRun, WatchlistItem


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def _analyze_payload(symbol: str = "DEMO", **config) -> dict:
    base = {
        "timeframe": "5m",
        "daily_history_days": 400,
        "intraday_history_days": 60,
    }
    base.update(config)
    return {"symbol": symbol, "config": base, "force": False}


@pytest.mark.django_db
def test_config_and_symbol_search(api: APIClient) -> None:
    response = api.get("/api/v1/market/config")
    assert response.status_code == 200
    assert response.json()["defaults"]["timeframe"] == "5m"
    assert response.json()["schema"]["sections"]
    assert response.json()["provider"]["name"] in {"synthetic", "yahoo", "alpaca"}

    response = api.get("/api/v1/market/symbols?q=DEM")
    assert response.status_code == 200
    symbols = [item["symbol"] for item in response.json()["results"]]
    assert "DEMO" in symbols


@pytest.mark.django_db
def test_ingest_is_incremental(api: APIClient) -> None:
    payload = {
        "symbol": "DEMO",
        "timeframe": "1d",
        "start": "2025-01-01T00:00:00Z",
        "end": "2025-06-01T00:00:00Z",
    }
    first = api.post("/api/v1/market/ingest", payload, format="json")
    assert first.status_code == 200, first.content
    first_data = first.json()
    assert first_data["fetched"] > 0
    assert first_data["bars"] > 0
    logs_after_first = FetchLog.objects.count()
    payload["end"] = first_data["coverage"]["latest_ts"]

    second = api.post("/api/v1/market/ingest", payload, format="json")
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["fetched"] == 0
    assert FetchLog.objects.count() == logs_after_first
    assert second_data["coverage"]["bar_count"] == first_data["coverage"]["bar_count"]


@pytest.mark.django_db
def test_analyze_endpoint_and_cache(api: APIClient) -> None:
    response = api.post(
        "/api/v1/market/analyze", _analyze_payload(), format="json"
    )
    assert response.status_code == 200, response.content
    profile = response.json()
    assert profile["meta"]["symbol"] == "DEMO"
    assert profile["rules"]
    assert profile["recommended"] is not None
    assert profile["cache"]["cached"] is False
    first_logs = FetchLog.objects.count()
    first_bars = Bar.objects.count()

    response2 = api.post(
        "/api/v1/market/analyze", _analyze_payload(), format="json"
    )
    assert response2.status_code == 200
    profile2 = response2.json()
    assert profile2["cache"]["cached"] is True
    assert FetchLog.objects.count() == first_logs
    assert Bar.objects.count() == first_bars
    assert profile2["recommended"]["rule_id"] == profile["recommended"]["rule_id"]


@pytest.mark.django_db
def test_analyze_daily_fallback(api: APIClient) -> None:
    response = api.post(
        "/api/v1/market/analyze",
        _analyze_payload(min_intraday_bars=100000),
        format="json",
    )
    assert response.status_code == 200, response.content
    profile = response.json()
    assert profile["meta"]["mode"] == "1d"
    assert profile["data"]["fallback"] is True
    assert any("fell back to daily" in warning for warning in profile["warnings"])


@pytest.mark.django_db
def test_watchlist_crud(api: APIClient) -> None:
    created = api.post(
        "/api/v1/market/watchlist",
        {"symbol": "DEMO", "note": "demo"},
        format="json",
    )
    assert created.status_code == 201
    assert WatchlistItem.objects.filter(security__symbol="DEMO").exists()

    listing = api.get("/api/v1/market/watchlist")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["security"]["symbol"] == "DEMO"

    deleted = api.delete("/api/v1/market/watchlist/DEMO")
    assert deleted.status_code == 204
    assert not WatchlistItem.objects.filter(security__symbol="DEMO").exists()


@pytest.mark.django_db
def test_live_check_and_chart(api: APIClient) -> None:
    analyzed = api.post(
        "/api/v1/market/analyze", _analyze_payload(), format="json"
    )
    assert analyzed.status_code == 200, analyzed.content

    live = api.post(
        "/api/v1/market/live-check",
        {"symbol": "DEMO", "config": {"timeframe": "5m"}},
        format="json",
    )
    assert live.status_code == 200, live.content
    data = live.json()
    assert data["signal_read"]["state"] in {"signal", "watching", "no_setup"}
    assert data["profile_summary"]["rule_id"]

    chart = api.get("/api/v1/market/chart/DEMO?timeframe=5m&limit=100")
    assert chart.status_code == 200
    assert len(chart.json()["bars"]) == 100


@pytest.mark.django_db
def test_screen_sync(api: APIClient) -> None:
    response = api.post(
        "/api/v1/market/screen",
        {
            "symbols": ["DEMO", "SYNTH-DOWN"],
            "config": {"daily_history_days": 400, "timeframe": "1d"},
            "sync": True,
            "limit": 2,
        },
        format="json",
    )
    assert response.status_code == 202, response.content
    body = response.json()
    assert body["status"] == "completed"
    assert len(body["results"]) == 2
    assert ScreenRun.objects.count() == 1
    statuses = {item["symbol"]: item["status"] for item in body["results"]}
    assert statuses["DEMO"] in {"qualified", "watch", "reject"}


@pytest.mark.django_db
def test_paper_tick_and_stats(api: APIClient) -> None:
    api.post("/api/v1/market/watchlist", {"symbol": "DEMO"}, format="json")
    analyzed = api.post(
        "/api/v1/market/analyze", _analyze_payload(), format="json"
    )
    assert analyzed.status_code == 200, analyzed.content

    tick = api.post(
        "/api/v1/market/paper/tick", {"symbols": ["DEMO"]}, format="json"
    )
    assert tick.status_code == 200, tick.content
    body = tick.json()
    assert body["actions"]
    assert body["actions"][0]["symbol"] == "DEMO"

    stats = api.get("/api/v1/market/paper/stats")
    assert stats.status_code == 200
    assert "win_rate" in stats.json()
    assert PaperTrade.objects.count() >= 0


@pytest.mark.django_db
def test_coverage_endpoint(api: APIClient) -> None:
    api.post(
        "/api/v1/market/ingest",
        {
            "symbol": "DEMO",
            "timeframe": "5m",
            "days": 10,
        },
        format="json",
    )
    response = api.get("/api/v1/market/coverage/DEMO?timeframe=5m")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "DEMO"
    assert "5m" in body["coverage"]
    assert body["coverage"]["5m"]["bar_count"] > 0
