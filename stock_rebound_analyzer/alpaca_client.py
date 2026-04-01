from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .models import DailyBar


class AlpacaMarketDataClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://data.alpaca.markets") -> None:
        if not api_key or not api_secret:
            raise ValueError("Alpaca credentials are required.")

        self.base_url = base_url.rstrip("/")
        try:
            import requests  # type: ignore
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency 'requests'. Install with: pip install -r requirements.txt"
            ) from exc

        self.session: Any = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            }
        )

    @classmethod
    def from_env(cls) -> "AlpacaMarketDataClient":
        api_key = os.getenv("ALPACA_API_KEY", "")
        api_secret = os.getenv("ALPACA_API_SECRET", "")
        base_url = os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")
        return cls(api_key=api_key, api_secret=api_secret, base_url=base_url)

    def fetch_daily_bars(self, symbol: str, start: str, end: str, adjustment: str = "raw") -> list[DailyBar]:
        endpoint = f"{self.base_url}/v2/stocks/bars"
        params: dict[str, Any] = {
            "symbols": symbol,
            "timeframe": "1Day",
            "start": start,
            "end": end,
            "adjustment": adjustment,
            "sort": "asc",
            "limit": 10000,
        }

        all_bars: list[DailyBar] = []
        page_token: str | None = None

        while True:
            if page_token:
                params["page_token"] = page_token
            elif "page_token" in params:
                params.pop("page_token")

            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()

            raw_bars = payload.get("bars", {}).get(symbol, [])
            for bar in raw_bars:
                all_bars.append(self._parse_bar(symbol=symbol, bar=bar))

            page_token = payload.get("next_page_token")
            if not page_token:
                break

        all_bars.sort(key=lambda b: b.date)
        return all_bars

    @staticmethod
    def _parse_bar(symbol: str, bar: dict[str, Any]) -> DailyBar:
        timestamp = str(bar["t"])
        day = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()

        return DailyBar(
            symbol=symbol,
            date=day,
            open=float(bar["o"]),
            high=float(bar["h"]),
            low=float(bar["l"]),
            close=float(bar["c"]),
            volume=int(bar["v"]),
        )
