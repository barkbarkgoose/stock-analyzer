"""Alpaca Market Data provider.

Alpaca is the better choice for multi-month intraday research, but the free
plan is usually IEX-only.  IEX sees a fraction of consolidated volume, so treat
volume/spread-dependent conclusions as approximate unless you have a SIP
subscription.  The provider honours ``ALPACA_FEED`` and ``ALPACA_ADJUSTMENT``.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from ..types import Bar
from .base import (
    DataProvider,
    ProviderConfigError,
    ProviderError,
    RateLimiter,
)

_TIMEFRAMES = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "30m": "30Min",
    "1h": "1Hour",
    "1d": "1Day",
}


class AlpacaProvider(DataProvider):
    name = "alpaca"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        feed: str | None = None,
        adjustment: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET", "")
        self.base_url = (
            base_url
            or os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")
        ).rstrip("/")
        self.feed = feed or os.getenv("ALPACA_FEED", "iex")
        self.adjustment = adjustment or os.getenv("ALPACA_ADJUSTMENT", "all")
        if not self.api_key or not self.api_secret:
            raise ProviderConfigError(
                "Alpaca requires ALPACA_API_KEY and ALPACA_API_SECRET."
            )
        try:
            import requests
        except ModuleNotFoundError as exc:
            raise ProviderError(
                "Missing dependency 'requests'. Install backend requirements."
            ) from exc
        self._requests = requests
        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.api_secret,
                "Accept": "application/json",
            }
        )
        self.limiter = RateLimiter(max_calls=180, period_seconds=60.0, min_interval=0.05)

    def describe(self) -> dict[str, object]:
        return {
            "name": "alpaca",
            "feed": self.feed,
            "adjustment": self.adjustment,
            "note": (
                "Free plans are typically IEX-only; volume and spreads are not "
                "consolidated. Historical depth depends on your plan."
            ),
        }

    def fetch_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]:
        if timeframe not in _TIMEFRAMES:
            raise ProviderError(f"Alpaca does not support timeframe {timeframe}")
        symbol = symbol.upper().strip()
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        endpoint = f"{self.base_url}/v2/stocks/bars"
        params: dict[str, object] = {
            "symbols": symbol,
            "timeframe": _TIMEFRAMES[timeframe],
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "adjustment": self.adjustment,
            "sort": "asc",
            "limit": 10000,
        }
        if self.feed:
            params["feed"] = self.feed

        bars: list[Bar] = []
        page_token: str | None = None
        for _ in range(200):
            if page_token:
                params["page_token"] = page_token
            else:
                params.pop("page_token", None)
            payload = self._request(endpoint, params)
            raw = payload.get("bars", {})
            if isinstance(raw, dict):
                rows = raw.get(symbol, []) or []
            else:
                rows = raw or []
            for row in rows:
                bar = self._parse_bar(symbol, row, timeframe)
                if bar is not None:
                    bars.append(bar)
            page_token = payload.get("next_page_token")
            if not page_token:
                break

        by_ts = {bar.ts: bar for bar in bars}
        return [by_ts[ts] for ts in sorted(by_ts)]

    def _request(self, endpoint: str, params: dict[str, object]) -> dict[str, object]:
        last_error: Exception | None = None
        for attempt in range(4):
            self.limiter.wait()
            try:
                response = self.session.get(endpoint, params=params, timeout=30)
                if response.status_code == 429:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if response.status_code in {401, 403}:
                    raise ProviderConfigError(
                        "Alpaca rejected the request. Check keys and feed "
                        f"(current feed={self.feed!r}). Some feeds require a paid plan."
                    )
                response.raise_for_status()
                return response.json()
            except ProviderConfigError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(1.0 * (attempt + 1))
        raise ProviderError(f"Alpaca request failed: {last_error}")

    @staticmethod
    def _parse_bar(
        symbol: str, row: dict[str, object], timeframe: str
    ) -> Bar | None:
        try:
            timestamp = datetime.fromisoformat(
                str(row["t"]).replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            open_price = float(row["o"])
            high = float(row["h"])
            low = float(row["l"])
            close = float(row["c"])
            volume = int(float(row.get("v", 0) or 0))
        except (KeyError, TypeError, ValueError):
            return None

        if timeframe == "1d":
            timestamp = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            from ..indicators import NY

            local = timestamp.astimezone(NY)
            minutes = local.hour * 60 + local.minute
            if not (9 * 60 + 30 <= minutes < 16 * 60):
                return None
        try:
            return Bar(
                symbol=symbol,
                ts=timestamp,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=max(0, volume),
                timeframe=timeframe,
                source="alpaca",
            )
        except ValueError:
            return None


__all__ = ["AlpacaProvider"]
