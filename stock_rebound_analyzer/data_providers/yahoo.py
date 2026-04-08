from __future__ import annotations

import datetime

from ..models import DailyBar, IntradayBar
from .base import DataProvider


class YahooDataProvider(DataProvider):
    def fetch_daily_bars(self, symbol: str, start: str, end: str) -> list[DailyBar]:
        try:
            import yfinance as yf
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency 'yfinance'. Install with: uv pip install yfinance"
            ) from exc

        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, auto_adjust=False)

        bars: list[DailyBar] = []
        for timestamp, row in df.iterrows():
            if isinstance(timestamp, datetime.datetime):
                trade_date = timestamp.date()
            else:
                trade_date = timestamp
            bars.append(
                DailyBar(
                    symbol=symbol.upper(),
                    date=trade_date,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                )
            )

        bars.sort(key=lambda b: b.date)
        return bars

    def fetch_intraday_bars(
        self, symbol: str, granularity: str, start: str, end: str
    ) -> list[IntradayBar]:
        try:
            import yfinance as yf
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency 'yfinance'. Install with: uv pip install yfinance"
            ) from exc

        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start,
            end=end,
            interval=granularity,
            auto_adjust=False,
        )

        bars: list[IntradayBar] = []
        for timestamp, row in df.iterrows():
            bars.append(
                IntradayBar(
                    symbol=symbol.upper(),
                    timestamp=self._normalize_timestamp(timestamp),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                )
            )

        bars.sort(key=lambda b: b.timestamp)
        return bars

    @staticmethod
    def _normalize_timestamp(value: object) -> datetime.datetime:
        timestamp = value
        if hasattr(timestamp, "to_pydatetime"):
            timestamp = timestamp.to_pydatetime()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError(f"Unsupported timestamp type returned by yfinance: {type(value)!r}")
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return timestamp
