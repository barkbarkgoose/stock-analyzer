from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from stock_rebound_analyzer.data import CachedDataProvider, DataCache
from stock_rebound_analyzer.data_providers.base import DataProvider
from stock_rebound_analyzer.models import DailyBar, IntradayBar


class DataCacheTests(unittest.TestCase):
    def test_creates_database_on_first_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cache" / "stock_cache.db"
            self.assertFalse(db_path.exists())

            DataCache(db_path=db_path)

            self.assertTrue(db_path.exists())

    def test_daily_and_intraday_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DataCache(db_path=Path(tmpdir) / "stock_cache.db")
            daily_bars = [
                DailyBar("AAPL", date(2026, 1, 2), 100.0, 101.0, 99.0, 100.5, 1_000),
                DailyBar("AAPL", date(2026, 1, 3), 100.5, 102.0, 100.0, 101.5, 1_200),
            ]
            intraday_bars = [
                IntradayBar(
                    "AAPL",
                    datetime(2026, 1, 2, 9, 30),
                    100.0,
                    100.2,
                    99.8,
                    100.1,
                    500,
                ),
                IntradayBar(
                    "AAPL",
                    datetime(2026, 1, 2, 9, 35),
                    100.1,
                    100.4,
                    100.0,
                    100.3,
                    550,
                ),
            ]

            cache.store_daily_bars("AAPL", daily_bars)
            cache.store_intraday_bars("AAPL", "5m", intraday_bars)

            self.assertEqual(
                cache.get_daily_bars("AAPL", date(2026, 1, 2), date(2026, 1, 3)),
                daily_bars,
            )
            self.assertEqual(
                cache.get_intraday_bars(
                    "AAPL",
                    "5m",
                    datetime(2026, 1, 2, 9, 30),
                    datetime(2026, 1, 2, 9, 35),
                ),
                intraday_bars,
            )
            self.assertTrue(
                cache.has_granularity(
                    "AAPL",
                    datetime(2026, 1, 2, 9, 30),
                    datetime(2026, 1, 2, 9, 35),
                    "5m",
                )
            )


class CachedDataProviderTests(unittest.TestCase):
    def test_fetch_daily_bars_only_loads_missing_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DataCache(db_path=Path(tmpdir) / "stock_cache.db")
            cache.store_daily_bars(
                "AAPL",
                [
                    DailyBar("AAPL", date(2026, 1, 2), 101.0, 102.0, 100.0, 101.5, 1_100),
                    DailyBar("AAPL", date(2026, 1, 3), 102.0, 103.0, 101.0, 102.5, 1_200),
                ],
                coverage_start=date(2026, 1, 2),
                coverage_end=date(2026, 1, 3),
            )
            provider = StubDataProvider(
                daily_responses={
                    ("AAPL", "2026-01-01", "2026-01-01"): [
                        DailyBar("AAPL", date(2026, 1, 1), 100.0, 101.0, 99.0, 100.5, 1_000)
                    ],
                    ("AAPL", "2026-01-04", "2026-01-05"): [
                        DailyBar("AAPL", date(2026, 1, 4), 103.0, 104.0, 102.0, 103.5, 1_300),
                        DailyBar("AAPL", date(2026, 1, 5), 104.0, 105.0, 103.0, 104.5, 1_400),
                    ],
                }
            )
            cached = CachedDataProvider(provider=provider, cache=cache)

            bars = cached.fetch_daily_bars("AAPL", "2026-01-01", "2026-01-05")

            self.assertEqual(
                provider.daily_calls,
                [
                    ("AAPL", "2026-01-01", "2026-01-01"),
                    ("AAPL", "2026-01-04", "2026-01-05"),
                ],
            )
            self.assertEqual([bar.date.isoformat() for bar in bars], [
                "2026-01-01",
                "2026-01-02",
                "2026-01-03",
                "2026-01-04",
                "2026-01-05",
            ])
            self.assertEqual(
                cached.fetch_daily_bars("AAPL", "2026-01-01", "2026-01-05"),
                bars,
            )
            self.assertEqual(len(provider.daily_calls), 2)

    def test_fetch_intraday_bars_augments_missing_granularity_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DataCache(db_path=Path(tmpdir) / "stock_cache.db")
            cache.store_intraday_bars(
                "MSFT",
                "5m",
                [
                    IntradayBar(
                        "MSFT",
                        datetime(2026, 1, 2, 9, 30),
                        200.0,
                        200.5,
                        199.8,
                        200.3,
                        400,
                    ),
                    IntradayBar(
                        "MSFT",
                        datetime(2026, 1, 2, 9, 35),
                        200.3,
                        200.7,
                        200.2,
                        200.6,
                        420,
                    ),
                ],
                coverage_start=datetime(2026, 1, 2, 9, 30),
                coverage_end=datetime(2026, 1, 2, 9, 35),
            )
            provider = StubDataProvider(
                intraday_responses={
                    ("MSFT", "5m", "2026-01-02T09:35:00", "2026-01-02T09:40:00"): [
                        IntradayBar(
                            "MSFT",
                            datetime(2026, 1, 2, 9, 40),
                            200.6,
                            201.0,
                            200.5,
                            200.9,
                            430,
                        )
                    ]
                }
            )
            cached = CachedDataProvider(provider=provider, cache=cache)

            bars = cached.fetch_intraday_bars(
                "MSFT",
                "5m",
                "2026-01-02T09:30:00",
                "2026-01-02T09:40:00",
            )

            self.assertEqual(
                provider.intraday_calls,
                [("MSFT", "5m", "2026-01-02T09:35:00", "2026-01-02T09:40:00")],
            )
            self.assertEqual(
                [bar.timestamp.isoformat(timespec="minutes") for bar in bars],
                ["2026-01-02T09:30", "2026-01-02T09:35", "2026-01-02T09:40"],
            )
            self.assertTrue(
                cache.has_granularity(
                    "MSFT",
                    datetime(2026, 1, 2, 9, 30),
                    datetime(2026, 1, 2, 9, 40),
                    "5m",
                )
            )


class StubDataProvider(DataProvider):
    def __init__(
        self,
        *,
        daily_responses: dict[tuple[str, str, str], list[DailyBar]] | None = None,
        intraday_responses: dict[tuple[str, str, str, str], list[IntradayBar]] | None = None,
    ) -> None:
        self.daily_responses = daily_responses or {}
        self.intraday_responses = intraday_responses or {}
        self.daily_calls: list[tuple[str, str, str]] = []
        self.intraday_calls: list[tuple[str, str, str, str]] = []

    def fetch_daily_bars(self, symbol: str, start: str, end: str) -> list[DailyBar]:
        key = (symbol, start, end)
        self.daily_calls.append(key)
        return list(self.daily_responses.get(key, []))

    def fetch_intraday_bars(
        self, symbol: str, granularity: str, start: str, end: str
    ) -> list[IntradayBar]:
        key = (symbol, granularity, start, end)
        self.intraday_calls.append(key)
        return list(self.intraday_responses.get(key, []))


if __name__ == "__main__":
    unittest.main()
