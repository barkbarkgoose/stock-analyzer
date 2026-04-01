from __future__ import annotations

import datetime

from ..models import DailyBar
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
