from __future__ import annotations

import unittest
from datetime import date, timedelta

from stock_rebound_analyzer.data_providers.base import DataProvider
from stock_rebound_analyzer.models import DailyBar
from stock_rebound_analyzer.screeners import ScanConfig
from stock_rebound_analyzer.selectors import (
    DayClassifier,
    DaySelectionConfig,
    DaySelector,
    DayType,
)


class DayClassifierTests(unittest.TestCase):
    def test_classifies_watch_triggered_day_types(self) -> None:
        classifier = DayClassifier()
        config = DaySelectionConfig(dip_threshold_pct=0.05)
        scenarios = {
            DayType.IMMEDIATE_REBOUND: make_bars(
                [
                    (100, 101, 99, 100),
                    (100, 99, 90, 98),
                ]
            ),
            DayType.GAP_DOWN_RECOVERY: make_bars(
                [
                    (100, 101, 99, 100),
                    (93, 99, 91, 98),
                ]
            ),
            DayType.CONTINUED_SELLOFF: make_bars(
                [
                    (100, 101, 99, 100),
                    (98, 99, 90, 90.5),
                ]
            ),
            DayType.TREND_DOWN_FAILURE: make_bars(
                [
                    (100, 101, 99, 100),
                    (99, 96, 90, 94),
                    (95, 96, 89.5, 92),
                ]
            ),
            DayType.CHOPPY_REVERSAL: make_bars(
                [
                    (100, 101, 99, 100),
                    (99, 97, 90, 95),
                    (95, 95.5, 94, 95),
                ]
            ),
        }

        for expected_day_type, bars in scenarios.items():
            with self.subTest(day_type=expected_day_type):
                results = classifier.classify_days(bars=bars, config=config)
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].day_type, expected_day_type)
                self.assertTrue(results[0].watch_triggered)
                self.assertGreaterEqual(results[0].dip_pct, 0.05)

    def test_filters_normal_vs_high_volatility_days(self) -> None:
        classifier = DayClassifier()
        bars = make_bars(
            [
                (100, 101, 99, 100),
                (100, 101, 99, 100.5),
                (100.5, 102, 93, 101),
            ]
        )

        normal_days = classifier.classify_days(
            bars=bars,
            config=DaySelectionConfig(
                dip_threshold_pct=0.05,
                day_types={DayType.NORMAL},
                include_normal_days=True,
                volatility_filter="normal",
                volatility_lookback_days=1,
                high_volatility_range_multiplier=1.5,
            ),
        )
        high_volatility_days = classifier.classify_days(
            bars=bars,
            config=DaySelectionConfig(
                dip_threshold_pct=0.05,
                day_types={DayType.IMMEDIATE_REBOUND},
                volatility_filter="high",
                volatility_lookback_days=1,
                high_volatility_range_multiplier=1.5,
            ),
        )

        self.assertEqual([day.day_type for day in normal_days], [DayType.NORMAL])
        self.assertEqual([day.date for day in normal_days], [date(2026, 1, 2)])
        self.assertEqual([day.day_type for day in high_volatility_days], [DayType.IMMEDIATE_REBOUND])
        self.assertEqual([day.date for day in high_volatility_days], [date(2026, 1, 3)])


class DaySelectorTests(unittest.TestCase):
    def test_select_qualifying_days_accepts_scan_config_thresholds(self) -> None:
        provider = StubDailyProvider(
            {
                "TEST": make_bars(
                    [
                        (100, 101, 99, 100),
                        (100, 99, 90, 98),
                        (98, 99, 97, 98.5),
                    ],
                    symbol="TEST",
                )
            }
        )
        selector = DaySelector(provider=provider)
        config = ScanConfig(
            min_dip_threshold_pct=5,
            min_dips_per_month=0,
            max_dips_per_week=0,
            rebound_target_pct=3,
            rebound_window_days=3,
            minimum_history_bars=2,
        )

        qualifying_days = selector.select_qualifying_days(
            symbol="TEST",
            start="2026-01-01",
            end="2026-01-31",
            config=config,
        )

        self.assertEqual(len(qualifying_days), 1)
        self.assertEqual(qualifying_days[0].day_type, DayType.IMMEDIATE_REBOUND)
        self.assertTrue(qualifying_days[0].watch_triggered)


class StubDailyProvider(DataProvider):
    def __init__(self, responses: dict[str, list[DailyBar]]) -> None:
        self.responses = {symbol.upper(): list(bars) for symbol, bars in responses.items()}

    def fetch_daily_bars(self, symbol: str, start: str, end: str) -> list[DailyBar]:
        return list(self.responses.get(symbol.upper(), []))


def make_bars(
    values: list[tuple[float, float, float, float]],
    *,
    symbol: str = "TEST",
    volume: int = 1_000_000,
) -> list[DailyBar]:
    current_date = date(2026, 1, 1)
    bars: list[DailyBar] = []

    for open_price, high, low, close in values:
        bars.append(
            DailyBar(
                symbol=symbol,
                date=current_date,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        current_date += timedelta(days=1)

    return bars


if __name__ == "__main__":
    unittest.main()
