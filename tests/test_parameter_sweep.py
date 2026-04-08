from __future__ import annotations

import unittest
from datetime import datetime

from stock_rebound_analyzer.backtests.parameter_sweep import (
    AggregationProfile,
    FREQ_SMALL_INCOME,
    BEST_RISK_ADJUSTED,
    SMOOTHER_COMPOUNDING,
    ParameterGrid,
    ParameterSweep,
    ResultAggregator,
    SweepResult,
)
from stock_rebound_analyzer.backtests.state_machine import BacktestResult, Trade
from stock_rebound_analyzer.models import IntradayBar


class ParameterGridTests(unittest.TestCase):
    def test_iter_combinations_small_grid(self) -> None:
        grid = ParameterGrid(
            trigger_drop_thresholds=[1.0, 2.0],
            rebound_confirmation_thresholds=[0.5, 1.0],
            profit_targets=[1.0],
            stop_losses=[1.0],
            cooldown_periods=[0],
            anchor_names=["previous_close"],
            time_stops=[10],
            bar_granularities=["5min"],
        )
        combos = grid.iter_combinations()
        self.assertEqual(len(combos), 4)
        self.assertIn(
            {
                "trigger_drop_thresholds": 1.0,
                "rebound_confirmation_thresholds": 0.5,
                "profit_targets": 1.0,
                "stop_losses": 1.0,
                "cooldown_periods": 0,
                "anchor_names": "previous_close",
                "time_stops": 10,
                "bar_granularities": "5min",
            },
            combos,
        )
        self.assertIn(
            {
                "trigger_drop_thresholds": 2.0,
                "rebound_confirmation_thresholds": 1.0,
                "profit_targets": 1.0,
                "stop_losses": 1.0,
                "cooldown_periods": 0,
                "anchor_names": "previous_close",
                "time_stops": 10,
                "bar_granularities": "5min",
            },
            combos,
        )

    def test_iter_combinations_empty_returns_empty(self) -> None:
        grid = ParameterGrid(
            trigger_drop_thresholds=[],
            rebound_confirmation_thresholds=[0.5],
        )
        combos = grid.iter_combinations()
        self.assertEqual(len(combos), 0)


class SweepResultTests(unittest.TestCase):
    def test_param_signature_generated(self) -> None:
        result = BacktestResult(trades=[], metrics={"total_trades": 0})
        params = {
            "trigger_drop_thresholds": 2.0,
            "rebound_confirmation_thresholds": 1.0,
            "profit_targets": 1.5,
            "stop_losses": 1.0,
            "cooldown_periods": 3,
            "anchor_names": "previous_close",
            "time_stops": 20,
            "bar_granularities": "5min",
        }
        sweep_result = SweepResult(params=params, result=result)
        self.assertIn("drop=2.0", sweep_result.param_signature)
        self.assertIn("rebound=1.0", sweep_result.param_signature)


class ResultAggregatorTests(unittest.TestCase):
    def test_get_best_returns_highest_score(self) -> None:
        results = [
            make_sweep_result(
                {
                    "total_trades": 10,
                    "win_rate": 0.6,
                    "average_pnl_pct": 1.5,
                    "max_drawdown_pct": -2.0,
                    "average_hold_bars": 5,
                }
            ),
            make_sweep_result(
                {
                    "total_trades": 20,
                    "win_rate": 0.7,
                    "average_pnl_pct": 2.0,
                    "max_drawdown_pct": -1.5,
                    "average_hold_bars": 8,
                }
            ),
            make_sweep_result(
                {
                    "total_trades": 5,
                    "win_rate": 0.5,
                    "average_pnl_pct": 1.0,
                    "max_drawdown_pct": -3.0,
                    "average_hold_bars": 3,
                }
            ),
        ]
        aggregator = ResultAggregator(results)
        best = aggregator.get_best(SMOOTHER_COMPOUNDING)
        self.assertEqual(best.result.metrics["total_trades"], 20)

    def test_get_top_n_returns_sorted_results(self) -> None:
        results = [
            make_sweep_result(
                {
                    "total_trades": 10,
                    "win_rate": 0.6,
                    "average_pnl_pct": 1.5,
                    "max_drawdown_pct": -2.0,
                    "average_hold_bars": 5,
                }
            ),
            make_sweep_result(
                {
                    "total_trades": 20,
                    "win_rate": 0.7,
                    "average_pnl_pct": 2.0,
                    "max_drawdown_pct": -1.5,
                    "average_hold_bars": 8,
                }
            ),
            make_sweep_result(
                {
                    "total_trades": 5,
                    "win_rate": 0.5,
                    "average_pnl_pct": 1.0,
                    "max_drawdown_pct": -3.0,
                    "average_hold_bars": 3,
                }
            ),
        ]
        aggregator = ResultAggregator(results)
        top2 = aggregator.get_top_n(SMOOTHER_COMPOUNDING, 2)
        self.assertEqual(len(top2), 2)
        self.assertEqual(top2[0].result.metrics["total_trades"], 20)

    def test_get_summary_table_formats_correctly(self) -> None:
        results = [
            make_sweep_result(
                {
                    "total_trades": 10,
                    "win_rate": 0.6,
                    "average_pnl_pct": 1.5,
                    "max_drawdown_pct": -2.0,
                    "max_gain_pct": 5.0,
                    "average_hold_bars": 5,
                }
            ),
        ]
        aggregator = ResultAggregator(results)
        table = aggregator.get_summary_table()
        self.assertEqual(len(table), 1)
        self.assertEqual(table[0]["total_trades"], 10)
        self.assertEqual(table[0]["win_rate"], "60.00%")
        self.assertEqual(table[0]["avg_pnl"], "1.500%")


class ParameterSweepIntegrationTests(unittest.TestCase):
    def test_run_small_grid(self) -> None:
        grid = ParameterGrid(
            trigger_drop_thresholds=[1.0, 2.0],
            rebound_confirmation_thresholds=[0.5],
            profit_targets=[1.0],
            stop_losses=[1.0],
            cooldown_periods=[0],
            anchor_names=["previous_close"],
            time_stops=[10],
            bar_granularities=["5min"],
        )

        def mock_loader(
            symbol: str, start: str, end: str, granularity: str
        ) -> list[IntradayBar]:
            return make_intraday_bars()

        sweep = ParameterSweep(bars_loader=mock_loader)
        results = sweep.run("TEST", "2026-01-01", "2026-01-31", grid)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIsInstance(r, SweepResult)
            self.assertIn("drop=", r.param_signature)


def make_sweep_result(metrics: dict) -> SweepResult:
    trades = []
    for i in range(metrics.get("total_trades", 0)):
        trades.append(
            Trade(
                entry_bar=i,
                entry_price=100.0,
                entry_reason="test",
                exit_bar=i + 1,
                exit_price=101.0,
                exit_reason="profit_target",
                pnl_pct=1.0,
                hold_bars=1,
            )
        )
    result = BacktestResult(trades=trades, metrics=metrics)
    params = {
        "trigger_drop_thresholds": 2.0,
        "rebound_confirmation_thresholds": 1.0,
        "profit_targets": 1.5,
        "stop_losses": 1.0,
        "cooldown_periods": 3,
        "anchor_names": "previous_close",
        "time_stops": 20,
        "bar_granularities": "5min",
    }
    return SweepResult(params=params, result=result)


def make_intraday_bars() -> list[IntradayBar]:
    base = datetime(2026, 1, 2, 9, 30)
    bars = []
    for i in range(78):
        total_minutes = 30 + i * 5
        hour = 9 + total_minutes // 60
        minute = total_minutes % 60
        if hour >= 24:
            hour = hour - 24
        ts = base.replace(hour=hour, minute=minute)
        bars.append(
            IntradayBar(
                symbol="TEST",
                timestamp=ts,
                open=100.0,
                high=100.5,
                low=99.0,
                close=100.2,
                volume=1000000,
            )
        )
    return bars


if __name__ == "__main__":
    unittest.main()
