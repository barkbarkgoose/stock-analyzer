from __future__ import annotations

import unittest
from datetime import date

from stock_rebound_analyzer.analysis import analyze_dip_rebounds
from stock_rebound_analyzer.models import DailyBar


class AnalyzeDipReboundsTests(unittest.TestCase):
    def test_detects_dips_and_successes(self) -> None:
        bars = [
            DailyBar("TEST", date(2026, 1, 1), 100, 101, 99, 100, 1000),
            DailyBar("TEST", date(2026, 1, 2), 95, 96, 94, 95, 1000),
            DailyBar("TEST", date(2026, 1, 3), 96, 98, 95, 97, 1000),
            DailyBar("TEST", date(2026, 1, 4), 97, 99, 96, 98, 1000),
            DailyBar("TEST", date(2026, 1, 5), 98, 99, 97, 98, 1000),
            DailyBar("TEST", date(2026, 1, 6), 98, 100, 97, 99, 1000),
            DailyBar("TEST", date(2026, 1, 7), 99, 100, 98, 99, 1000),
        ]

        report = analyze_dip_rebounds(
            symbol="TEST",
            bars=bars,
            dip_threshold_pct=0.05,
            rebound_target_pct=0.03,
            rebound_window_days=3,
        )

        self.assertEqual(report.dip_count, 1)
        self.assertEqual(report.resolved_dip_count, 1)
        self.assertEqual(report.completed_window_count, 1)
        self.assertEqual(report.success_count, 1)
        self.assertAlmostEqual(report.success_rate, 1.0)
        self.assertGreaterEqual(report.confidence_low, 0.0)
        self.assertLessEqual(report.confidence_high, 1.0)

    def test_returns_zero_stats_when_no_events(self) -> None:
        bars = [
            DailyBar("TEST", date(2026, 1, 1), 100, 101, 99, 100, 1000),
            DailyBar("TEST", date(2026, 1, 2), 100, 101, 99, 100.5, 1000),
            DailyBar("TEST", date(2026, 1, 3), 100, 101, 99, 100.2, 1000),
            DailyBar("TEST", date(2026, 1, 4), 100, 101, 99, 100.3, 1000),
        ]

        report = analyze_dip_rebounds(
            symbol="TEST",
            bars=bars,
            dip_threshold_pct=0.05,
            rebound_target_pct=0.03,
            rebound_window_days=2,
        )

        self.assertEqual(report.dip_count, 0)
        self.assertEqual(report.resolved_dip_count, 0)
        self.assertEqual(report.completed_window_count, 0)
        self.assertEqual(report.success_count, 0)
        self.assertEqual(report.success_rate, 0.0)
        self.assertEqual(report.confidence_low, 0.0)
        self.assertEqual(report.confidence_high, 0.0)

    def test_keeps_recent_dips_open_without_lookahead(self) -> None:
        bars = [
            DailyBar("TEST", date(2026, 1, 1), 100, 101, 99, 100, 1000),
            DailyBar("TEST", date(2026, 1, 2), 95, 96, 94, 95, 1000),
            DailyBar("TEST", date(2026, 1, 3), 95, 96, 94, 95, 1000),
        ]

        report = analyze_dip_rebounds(
            symbol="TEST",
            bars=bars,
            dip_threshold_pct=0.05,
            rebound_target_pct=0.03,
            rebound_window_days=3,
        )

        self.assertEqual(report.dip_count, 1)
        self.assertEqual(report.resolved_dip_count, 0)
        self.assertEqual(report.completed_window_count, 0)
        self.assertEqual(report.success_count, 0)
        self.assertEqual(report.success_rate, 0.0)

        event = report.dip_events[0]
        self.assertEqual(event.observed_days, 1)
        self.assertFalse(event.window_complete)
        self.assertFalse(event.historical_success)
        self.assertIsNone(event.historical_days_to_target)

    def test_counts_early_target_hit_as_resolved_without_full_window(self) -> None:
        bars = [
            DailyBar("TEST", date(2026, 1, 1), 100, 101, 99, 100, 1000),
            DailyBar("TEST", date(2026, 1, 2), 95, 96, 94, 95, 1000),
            DailyBar("TEST", date(2026, 1, 3), 97, 99, 96, 98, 1000),
        ]

        report = analyze_dip_rebounds(
            symbol="TEST",
            bars=bars,
            dip_threshold_pct=0.05,
            rebound_target_pct=0.03,
            rebound_window_days=3,
        )

        self.assertEqual(report.dip_count, 1)
        self.assertEqual(report.resolved_dip_count, 1)
        self.assertEqual(report.completed_window_count, 0)
        self.assertEqual(report.success_count, 1)
        self.assertAlmostEqual(report.success_rate, 1.0)

        event = report.dip_events[0]
        self.assertEqual(event.observed_days, 1)
        self.assertFalse(event.window_complete)
        self.assertTrue(event.historical_success)
        self.assertEqual(event.historical_days_to_target, 1)


if __name__ == "__main__":
    unittest.main()
