from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.market.models import Bar, DataCoverage, FetchLog
from apps.market.services import bars as bars_service
from stock_rebound_analyzer.providers.synthetic import synthetic_bars


class FakeProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    def fetch_bars(self, symbol, timeframe, start, end):
        return synthetic_bars(symbol, timeframe, start, end)

    def oldest_available(self, timeframe):
        return None

    def describe(self):
        return {"name": self.name}


@pytest.mark.django_db
def test_switching_provider_resets_cache(monkeypatch) -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 3, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(
        bars_service, "get_market_provider", lambda source=None: FakeProvider("fake-a")
    )
    first = bars_service.ensure_bars("DEMO", "1d", start, end)
    assert first.fetched > 0
    assert first.coverage["provider"] == "fake-a"
    first_version = first.security.data_version
    first_bar_count = Bar.objects.count()
    assert first_bar_count > 0

    monkeypatch.setattr(
        bars_service, "get_market_provider", lambda source=None: FakeProvider("fake-b")
    )
    second = bars_service.ensure_bars("DEMO", "1d", start, end)
    assert second.fetched > 0
    assert second.coverage["provider"] == "fake-b"
    assert second.security.data_version > first_version
    assert any("Provider changed" in warning for warning in second.warnings)
    assert Bar.objects.count() == first_bar_count
    assert FetchLog.objects.filter(source="fake-a").exists()
    assert FetchLog.objects.filter(source="fake-b").exists()
    assert DataCoverage.objects.get(timeframe="1d").provider == "fake-b"


@pytest.mark.django_db
def test_repeated_request_does_not_refetch_covered_history(monkeypatch) -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 3, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        bars_service, "get_market_provider", lambda source=None: FakeProvider("fake-a")
    )
    first = bars_service.ensure_bars("DEMO", "1d", start, end)
    assert first.fetched > 0
    logs = FetchLog.objects.count()
    # Use the actual cached latest timestamp so the request is fully covered.
    covered_end = first.coverage["latest_ts"]
    second = bars_service.ensure_bars(
        "DEMO", "1d", start, datetime.fromisoformat(covered_end)
    )
    assert second.fetched == 0
    assert FetchLog.objects.count() == logs
