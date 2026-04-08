from __future__ import annotations

import unittest
from datetime import date, timedelta

from stock_rebound_analyzer.data_providers.base import DataProvider
from stock_rebound_analyzer.models import DailyBar
from stock_rebound_analyzer.screeners import ScanConfig, UniverseScanner


class UniverseScannerTests(unittest.TestCase):
    def test_scan_ranks_rebound_candidates_and_exposes_breakdown(self) -> None:
        provider = StubDailyProvider(
            {
                "STRONG": build_bars(
                    "STRONG",
                    [
                        100, 94, 98, 101, 103,
                        103, 97, 101, 104, 106,
                        106, 100, 104, 107, 109,
                        109, 103, 107, 110, 112,
                    ],
                    volume=1_500_000,
                ),
                "WEAK": build_bars(
                    "WEAK",
                    [
                        100, 94, 93, 92, 91,
                        91, 85, 84, 83, 82,
                        82, 77, 76, 75, 74,
                        74, 69, 68, 67, 66,
                    ],
                    volume=1_500_000,
                ),
            }
        )
        scanner = UniverseScanner(provider=provider)
        config = ScanConfig(
            min_dip_threshold_pct=0.05,
            min_dips_per_month=1.5,
            max_dips_per_week=1.25,
            rebound_target_pct=0.03,
            rebound_window_days=3,
            minimum_history_bars=10,
            volatility_range=(0.05, 1.5),
        )

        results = scanner.scan(
            ["weak", "strong"],
            start="2026-01-01",
            end="2026-02-01",
            config=config,
        )

        self.assertEqual([candidate.symbol for candidate in results], ["STRONG", "WEAK"])
        self.assertGreater(results[0].score, results[1].score)
        self.assertEqual(results[0].breakdown["status"], "ok")
        self.assertTrue(results[0].breakdown["eligible"])
        self.assertIn("component_scores", results[0].breakdown)
        self.assertIn("metrics", results[0].breakdown)
        self.assertGreater(results[0].profile.average_rebound_pct, 0.03)
        self.assertGreater(results[0].breakdown["metrics"]["success_rate"], 0.5)
        self.assertLess(results[1].breakdown["metrics"]["success_rate"], 0.5)

    def test_scan_filters_low_liquidity_candidates(self) -> None:
        provider = StubDailyProvider(
            {
                "LIQ": build_bars(
                    "LIQ",
                    [100, 94, 98, 100, 101, 101, 95, 99, 101, 103, 103, 97, 101, 103],
                    volume=100,
                )
            }
        )
        scanner = UniverseScanner(provider=provider)
        config = ScanConfig(
            min_dip_threshold_pct=5,
            min_dips_per_month=1,
            max_dips_per_week=2,
            liquidity_filter=50_000,
            rebound_target_pct=3,
            rebound_window_days=3,
            minimum_history_bars=10,
        )

        results = scanner.scan(
            ["LIQ"],
            start="2026-01-01",
            end="2026-01-31",
            config=config,
        )

        candidate = results[0]
        self.assertEqual(candidate.breakdown["status"], "filtered")
        self.assertFalse(candidate.breakdown["eligible"])
        self.assertIn("below_liquidity_filter", candidate.breakdown["flags"])
        self.assertLess(candidate.score, 50)

    def test_scan_handles_missing_data_and_provider_errors_gracefully(self) -> None:
        provider = StubDailyProvider({"GOOD": build_bars("GOOD", [100, 94, 98, 100, 101, 101, 95, 99, 101, 103])})
        provider.error_symbols.add("ERR")
        scanner = UniverseScanner(provider=provider)
        config = ScanConfig(
            min_dip_threshold_pct=0.05,
            min_dips_per_month=1,
            max_dips_per_week=2,
            rebound_target_pct=0.03,
            rebound_window_days=3,
            minimum_history_bars=5,
        )

        results = scanner.scan(
            ["MISS", "ERR", "GOOD"],
            start="2026-01-01",
            end="2026-01-31",
            config=config,
        )
        indexed = {candidate.symbol: candidate for candidate in results}

        self.assertEqual(indexed["MISS"].breakdown["status"], "insufficient_data")
        self.assertEqual(indexed["MISS"].score, 0.0)
        self.assertEqual(indexed["MISS"].profile.total_bars, 0)

        self.assertEqual(indexed["ERR"].breakdown["status"], "error")
        self.assertEqual(indexed["ERR"].score, 0.0)
        self.assertIn("boom for ERR", indexed["ERR"].breakdown["reason"])

        self.assertEqual(indexed["GOOD"].breakdown["status"], "ok")
        self.assertGreater(indexed["GOOD"].score, 0.0)


class StubDailyProvider(DataProvider):
    def __init__(self, responses: dict[str, list[DailyBar]]) -> None:
        self.responses = {symbol.upper(): list(bars) for symbol, bars in responses.items()}
        self.error_symbols: set[str] = set()

    def fetch_daily_bars(self, symbol: str, start: str, end: str) -> list[DailyBar]:
        normalized_symbol = symbol.upper()
        if normalized_symbol in self.error_symbols:
            raise RuntimeError(f"boom for {normalized_symbol}")
        return list(self.responses.get(normalized_symbol, []))


def build_bars(symbol: str, closes: list[float], volume: int = 1_000_000) -> list[DailyBar]:
    bars: list[DailyBar] = []
    current_date = date(2026, 1, 1)

    for index, close in enumerate(closes):
        previous_close = closes[index - 1] if index > 0 else close
        open_price = previous_close
        high = max(open_price, close) * 1.02
        low = min(open_price, close) * 0.98
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
