from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..backtests.parameter_sweep import SweepResult
from ..backtests.state_machine import BacktestResult
from ..metrics.calculator import MetricsCalculator, TimeHorizonDistribution


@dataclass
class ComparisonResult:
    best_frequent_small_income: Optional[SweepResult]
    best_smoother_longer_term: Optional[SweepResult]
    best_risk_adjusted: Optional[SweepResult]
    comparison_table: list[dict]


class ReportFormatter:
    def __init__(self, result: BacktestResult):
        self.result = result
        self.calculator = MetricsCalculator(result)

    def format_summary(self) -> str:
        metrics = self.calculator.compute_all()
        lines = [
            "=" * 60,
            "BACKTEST SUMMARY",
            "=" * 60,
            f"Total Trades:        {metrics['total_trades']:.0f}",
            f"Trades/Week:         {metrics['trades_per_week']:.2f}",
            f"Trades/Month:        {metrics['trades_per_month']:.2f}",
            f"Win Rate:            {metrics['win_rate']:.2%}",
            f"Average Win:         {metrics['average_win']:.3f}%",
            f"Average Loss:        {metrics['average_loss']:.3f}%",
            f"Expectancy:          {metrics['expectancy']:.3f}%",
            f"Total Return:        {metrics['total_return']:.3f}%",
            f"Max Drawdown:        {metrics['max_drawdown']:.3f}%",
            f"Profit Factor:       {metrics['profit_factor']:.3f}",
            f"Avg Hold Time:       {metrics['average_hold_time']:.2f} bars",
            f"Time in Market:      {metrics['time_in_market']:.2%}",
            f"Capital Usage:       {metrics['capital_usage']:.3f}",
            "=" * 60,
        ]
        return "\n".join(lines)

    def format_detailed(self) -> str:
        metrics = self.calculator.compute_all()
        distributions = self.calculator.compute_time_horizon_distributions()

        lines = [
            "=" * 60,
            "DETAILED BACKTEST REPORT",
            "=" * 60,
            "",
            "--- Core Metrics ---",
            f"Total Trades:        {metrics['total_trades']:.0f}",
            f"Trades/Week:         {metrics['trades_per_week']:.2f}",
            f"Trades/Month:        {metrics['trades_per_month']:.2f}",
            "",
            "--- Win/Loss Analysis ---",
            f"Win Rate:            {metrics['win_rate']:.2%}",
            f"Average Win:         {metrics['average_win']:.3f}%",
            f"Average Loss:        {metrics['average_loss']:.3f}%",
            f"Expectancy:          {metrics['expectancy']:.3f}%",
            "",
            "--- Overall Performance ---",
            f"Total Return:        {metrics['total_return']:.3f}%",
            f"Max Drawdown:        {metrics['max_drawdown']:.3f}%",
            f"Profit Factor:       {metrics['profit_factor']:.3f}",
            "",
            "--- Time Analysis ---",
            f"Average Hold Time:   {metrics['average_hold_time']:.2f} bars",
            f"Time in Market:      {metrics['time_in_market']:.2%}",
            f"Capital Usage:       {metrics['capital_usage']:.3f}",
            "",
            "--- Monthly Distribution ---",
        ]

        for key, val in sorted(distributions.monthly.items()):
            lines.append(f"  {key}: {val:.3f}%")
        if not distributions.monthly:
            lines.append("  (no data)")

        lines.extend(
            [
                "",
                "--- Quarterly Distribution ---",
            ]
        )
        for key in sorted(distributions.quarterly.keys()):
            lines.append(f"  {key}: {distributions.quarterly[key]:.3f}%")
        if not distributions.quarterly:
            lines.append("  (no data)")

        lines.extend(
            [
                "",
                "--- Yearly Distribution ---",
            ]
        )
        for key in sorted(distributions.yearly.keys()):
            lines.append(f"  {key}: {distributions.yearly[key]:.3f}%")
        if not distributions.yearly:
            lines.append("  (no data)")

        lines.append("=" * 60)
        return "\n".join(lines)

    @staticmethod
    def compare_parameter_sets(results: list[SweepResult]) -> ComparisonResult:
        if not results:
            return ComparisonResult(None, None, None, [])

        valid_results = [r for r in results if r.result.trades]
        if not valid_results:
            return ComparisonResult(None, None, None, [])

        scoring = []
        for result in valid_results:
            calc = MetricsCalculator(result.result)
            metrics = calc.compute_all()
            scoring.append(
                (
                    result,
                    {
                        "total_trades": metrics["total_trades"],
                        "win_rate": metrics["win_rate"],
                        "average_pnl_pct": metrics["expectancy"],
                        "max_drawdown_pct": metrics["max_drawdown"],
                        "average_hold_bars": metrics["average_hold_time"],
                    },
                )
            )

        def score_for_profile(r: SweepResult, profile: str) -> float:
            s = next(s for result, s in scoring if result is r)
            if profile == "frequent_small_income":
                return (
                    s["total_trades"] * 0.4
                    + s["win_rate"] * 100 * 0.3
                    + s["average_pnl_pct"] * 0.2
                    + s["max_drawdown_pct"] * -0.1
                )
            elif profile == "smoother_longer_term":
                return (
                    s["win_rate"] * 100 * 0.3
                    + s["average_pnl_pct"] * 0.25
                    + s["max_drawdown_pct"] * -0.3
                    + s["average_hold_bars"] * 0.15
                )
            else:
                return (
                    s["win_rate"] * 100 * 0.35
                    + s["average_pnl_pct"] * 0.25
                    + s["max_drawdown_pct"] * -0.4
                )

        best_freq = max(
            valid_results,
            key=lambda r: score_for_profile(r, "frequent_small_income"),
            default=None,
        )
        best_smooth = max(
            valid_results,
            key=lambda r: score_for_profile(r, "smoother_longer_term"),
            default=None,
        )
        best_risk = max(
            valid_results,
            key=lambda r: score_for_profile(r, "best_risk_adjusted"),
            default=None,
        )

        comparison_table = []
        for result in valid_results:
            calc = MetricsCalculator(result.result)
            metrics = calc.compute_all()
            comparison_table.append(
                {
                    "signature": result.param_signature,
                    "total_trades": metrics["total_trades"],
                    "trades_per_week": metrics["trades_per_week"],
                    "trades_per_month": metrics["trades_per_month"],
                    "win_rate": metrics["win_rate"],
                    "expectancy": metrics["expectancy"],
                    "total_return": metrics["total_return"],
                    "max_drawdown": metrics["max_drawdown"],
                    "profit_factor": metrics["profit_factor"],
                    "avg_hold_time": metrics["average_hold_time"],
                }
            )

        return ComparisonResult(
            best_frequent_small_income=best_freq,
            best_smoother_longer_term=best_smooth,
            best_risk_adjusted=best_risk,
            comparison_table=comparison_table,
        )

    @staticmethod
    def format_comparison(comparison: ComparisonResult) -> str:
        lines = [
            "=" * 80,
            "PARAMETER SET COMPARISON",
            "=" * 80,
        ]

        if comparison.best_frequent_small_income:
            r = comparison.best_frequent_small_income
            lines.append("")
            lines.append("Best for Frequent Small Income:")
            lines.append(f"  {r.param_signature}")
            calc = MetricsCalculator(r.result)
            m = calc.compute_all()
            lines.append(
                f"  Trades: {m['total_trades']:.0f}, Win Rate: {m['win_rate']:.2%}, Expectancy: {m['expectancy']:.3f}%"
            )

        if comparison.best_smoother_longer_term:
            r = comparison.best_smoother_longer_term
            lines.append("")
            lines.append("Best for Smoother Longer-Term Compounding:")
            lines.append(f"  {r.param_signature}")
            calc = MetricsCalculator(r.result)
            m = calc.compute_all()
            lines.append(
                f"  Trades: {m['total_trades']:.0f}, Win Rate: {m['win_rate']:.2%}, Max Drawdown: {m['max_drawdown']:.3f}%"
            )

        if comparison.best_risk_adjusted:
            r = comparison.best_risk_adjusted
            lines.append("")
            lines.append("Best Risk-Adjusted Profile:")
            lines.append(f"  {r.param_signature}")
            calc = MetricsCalculator(r.result)
            m = calc.compute_all()
            lines.append(
                f"  Trades: {m['total_trades']:.0f}, Win Rate: {m['win_rate']:.2%}, Profit Factor: {m['profit_factor']:.3f}"
            )

        lines.append("")
        lines.append("-" * 80)
        lines.append(
            f"{'Signature':<40} {'Trades':>8} {'Win%':>8} {'Exp%':>10} {'MaxDD%':>10} {'PF':>8}"
        )
        lines.append("-" * 80)

        for row in comparison.comparison_table:
            lines.append(
                f"{row['signature']:<40} "
                f"{row['total_trades']:>8.0f} "
                f"{row['win_rate']:>8.2%} "
                f"{row['expectancy']:>10.3f} "
                f"{row['max_drawdown']:>10.3f} "
                f"{row['profit_factor']:>8.3f}"
            )

        lines.append("=" * 80)
        return "\n".join(lines)
