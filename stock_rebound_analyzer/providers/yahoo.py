"""Yahoo Finance provider (free, unofficial, best-effort).

Yahoo's intraday history is limited: roughly 7 days for 1-minute bars and 60
days for 5/15/30-minute bars.  Daily history is effectively unbounded.  The
service caches every fetched bar, so running the tool over time accumulates a
longer 5-minute history than Yahoo will serve in one request.
"""

from __future__ import annotations

import math
import time
import warnings
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..types import Bar
from .base import DataProvider, ProviderError, RateLimiter, utc_now

NY = ZoneInfo("America/New_York")

_INTERVALS = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "1d": "1d",
}

_CHUNK_DAYS = {
    "1m": 6,
    "5m": 58,
    "15m": 58,
    "30m": 58,
    "1h": 720,
    "1d": 3650,
}


class YahooProvider(DataProvider):
    name = "yahoo"

    def __init__(self) -> None:
        self.limiter = RateLimiter(max_calls=4, period_seconds=1.0, min_interval=0.25)

    def oldest_available(self, timeframe: str) -> datetime | None:
        now = utc_now()
        if timeframe == "1m":
            return now - timedelta(days=6)
        if timeframe in {"5m", "15m", "30m"}:
            return now - timedelta(days=58)
        if timeframe == "1h":
            return now - timedelta(days=720)
        return None

    def describe(self) -> dict[str, object]:
        return {
            "name": "yahoo",
            "note": (
                "Free unofficial provider. 1m bars ~7 days, 5/15/30m ~60 days, "
                "1h ~730 days. Cached bars are retained, so history accumulates."
            ),
        }

    def fetch_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Bar]:
        if timeframe not in _INTERVALS:
            raise ProviderError(f"Yahoo does not support timeframe {timeframe}")
        try:
            import yfinance as yf
        except ModuleNotFoundError as exc:
            raise ProviderError(
                "Missing dependency 'yfinance'. Install backend requirements."
            ) from exc

        symbol = symbol.upper().strip()
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        # Clamp to what Yahoo can actually serve.  The service records the
        # provider limit so it does not re-request impossible ranges forever.
        oldest = self.oldest_available(timeframe)
        requested_start = start
        if oldest is not None and start < oldest:
            start = oldest

        chunk_days = _CHUNK_DAYS[timeframe]
        interval = _INTERVALS[timeframe]
        bars: list[Bar] = []
        cursor = start
        while cursor < end:
            chunk_end = min(end, cursor + timedelta(days=chunk_days))
            df = self._fetch_chunk(
                yf, symbol, interval, cursor, chunk_end, timeframe
            )
            bars.extend(df)
            cursor = chunk_end

        # De-duplicate and sort.
        by_ts = {bar.ts: bar for bar in bars}
        result = [by_ts[ts] for ts in sorted(by_ts)]
        if oldest is not None and requested_start < oldest:
            # The caller can see this from describe()/coverage; we simply
            # return what exists.
            pass
        return result

    def _fetch_chunk(
        self,
        yf: object,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[Bar]:
        last_error: Exception | None = None
        for attempt in range(3):
            self.limiter.wait()
            try:
                with warnings.catch_warnings():
                    # yfinance currently emits pandas-4 deprecation warnings
                    # from its internals; they are not actionable for this app.
                    warnings.simplefilter("ignore")
                    ticker = yf.Ticker(symbol)  # type: ignore[attr-defined]
                    df = ticker.history(
                        start=start.date().isoformat(),
                        end=(end + timedelta(days=1)).date().isoformat(),
                        interval=interval,
                        auto_adjust=True,
                        actions=False,
                        prepost=False,
                        raise_errors=True,
                        timeout=20,
                    )
                return self._parse_frame(df, symbol, timeframe)
            except Exception as exc:  # yfinance raises many exception types
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise ProviderError(f"Yahoo request failed for {symbol}: {last_error}")

    @staticmethod
    def _parse_frame(df: object, symbol: str, timeframe: str) -> list[Bar]:
        if df is None or getattr(df, "empty", True):
            return []
        bars: list[Bar] = []
        for timestamp, row in df.iterrows():  # type: ignore[union-attr]
            try:
                open_price = float(row["Open"])
                high = float(row["High"])
                low = float(row["Low"])
                close = float(row["Close"])
            except (KeyError, TypeError, ValueError):
                continue
            if not all(
                math.isfinite(v) and v > 0
                for v in (open_price, high, low, close)
            ):
                continue
            try:
                volume = int(float(row.get("Volume", 0) or 0))
            except (TypeError, ValueError):
                volume = 0

            if timeframe == "1d":
                if hasattr(timestamp, "date"):
                    day = timestamp.date()
                else:
                    day = timestamp
                ts = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            else:
                if hasattr(timestamp, "to_pydatetime"):
                    dt = timestamp.to_pydatetime()
                else:
                    dt = timestamp
                if not isinstance(dt, datetime):
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=NY)
                ts = dt.astimezone(timezone.utc)
                local = ts.astimezone(NY)
                minutes = local.hour * 60 + local.minute
                if not (9 * 60 + 30 <= minutes < 16 * 60):
                    continue

            try:
                bars.append(
                    Bar(
                        symbol=symbol,
                        ts=ts,
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        volume=max(0, volume),
                        timeframe=timeframe,
                        source="yahoo",
                    )
                )
            except ValueError:
                continue
        return bars


__all__ = ["YahooProvider"]
