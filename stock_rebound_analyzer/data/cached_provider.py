from __future__ import annotations

from datetime import date, datetime

from ..models import DailyBar, IntradayBar
from ..data_providers.base import DataProvider
from .cache import DataCache, _coerce_date, _coerce_datetime


class CachedDataProvider(DataProvider):
    def __init__(self, provider: DataProvider, cache: DataCache | None = None) -> None:
        self.provider = provider
        self.cache = cache or DataCache()

    def fetch_daily_bars(self, symbol: str, start: str, end: str) -> list[DailyBar]:
        normalized_symbol = symbol.upper()
        start_date = _coerce_date(start)
        end_date = _coerce_date(end)

        for missing_range in self.cache.get_missing_daily_ranges(normalized_symbol, start_date, end_date):
            fetched = self.provider.fetch_daily_bars(
                symbol=normalized_symbol,
                start=missing_range.start.isoformat(),
                end=missing_range.end.isoformat(),
            )
            self.cache.store_daily_bars(
                normalized_symbol,
                fetched,
                coverage_start=missing_range.start,
                coverage_end=missing_range.end,
            )

        return self.cache.get_daily_bars(normalized_symbol, start_date, end_date)

    def fetch_intraday_bars(
        self, symbol: str, granularity: str, start: str, end: str
    ) -> list[IntradayBar]:
        normalized_symbol = symbol.upper()
        start_at = _coerce_datetime(start, is_end=False)
        end_at = _coerce_datetime(end, is_end=True)

        for missing_range in self.cache.get_missing_intraday_ranges(
            normalized_symbol,
            granularity,
            start_at,
            end_at,
        ):
            fetched = self.provider.fetch_intraday_bars(
                symbol=normalized_symbol,
                granularity=granularity,
                start=_format_datetime(missing_range.start),
                end=_format_datetime(missing_range.end),
            )
            self.cache.store_intraday_bars(
                normalized_symbol,
                granularity,
                fetched,
                coverage_start=missing_range.start,
                coverage_end=missing_range.end,
            )

        return self.cache.get_intraday_bars(normalized_symbol, granularity, start_at, end_at)



def _format_datetime(value: datetime | date) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value.isoformat()
