from __future__ import annotations

from .base import DataProvider
from ..alpaca_client import AlpacaMarketDataClient
from ..models import DailyBar


class AlpacaDataProvider(DataProvider):
    def fetch_daily_bars(self, symbol: str, start: str, end: str) -> list[DailyBar]:
        client = AlpacaMarketDataClient.from_env()
        return client.fetch_daily_bars(symbol=symbol, start=start, end=end)
