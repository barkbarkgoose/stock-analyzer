from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..backtests.state_machine import BacktestResult, Trade


@dataclass
class TimeHorizonDistribution:
    monthly: dict[str, float]
    quarterly: dict[str, float]
    yearly: dict[str, float]


class MetricsCalculator:
    def __init__(self, result: BacktestResult):
        self.result = result
        self.trades = result.trades

    def compute_all(self) -> dict:
        return {
            "total_trades": self.total_trades(),
            "trades_per_week": self.trades_per_week(),
            "trades_per_month": self.trades_per_month(),
            "win_rate": self.win_rate(),
            "average_win": self.average_win(),
            "average_loss": self.average_loss(),
            "expectancy": self.expectancy(),
            "total_return": self.total_return(),
            "max_drawdown": self.max_drawdown(),
            "profit_factor": self.profit_factor(),
            "average_hold_time": self.average_hold_time(),
            "time_in_market": self.time_in_market(),
            "capital_usage": self.capital_usage(),
        }

    def total_trades(self) -> int:
        return len(self.trades)

    def trades_per_week(self) -> float:
        if not self.trades or len(self.trades) < 2:
            return 0.0
        bar_range = self._bar_range()
        if bar_range == 0:
            return 0.0
        weeks = bar_range / (78 * 5)
        return len(self.trades) / weeks if weeks > 0 else 0.0

    def trades_per_month(self) -> float:
        if not self.trades or len(self.trades) < 2:
            return 0.0
        bar_range = self._bar_range()
        if bar_range == 0:
            return 0.0
        months = bar_range / (78 * 20)
        return len(self.trades) / months if months > 0 else 0.0

    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        winners = self._winners()
        return len(winners) / len(self.trades) if self.trades else 0.0

    def average_win(self) -> float:
        winners = self._winners()
        if not winners:
            return 0.0
        pnls = [t.pnl_pct for t in winners if t.pnl_pct is not None]
        return sum(pnls) / len(pnls) if pnls else 0.0

    def average_loss(self) -> float:
        losers = self._losers()
        if not losers:
            return 0.0
        pnls = [t.pnl_pct for t in losers if t.pnl_pct is not None]
        return sum(pnls) / len(pnls) if pnls else 0.0

    def expectancy(self) -> float:
        if not self.trades:
            return 0.0
        win_rate = self.win_rate()
        avg_win = self.average_win()
        avg_loss = self.average_loss()
        return (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    def total_return(self) -> float:
        if not self.trades:
            return 0.0
        pnls = [t.pnl_pct for t in self.trades if t.pnl_pct is not None]
        return sum(pnls) if pnls else 0.0

    def max_drawdown(self) -> float:
        if not self.trades:
            return 0.0
        pnls = [t.pnl_pct for t in self.trades if t.pnl_pct is not None]
        return min(pnls) if pnls else 0.0

    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl_pct for t in self._winners() if t.pnl_pct is not None)
        gross_loss = abs(
            sum(t.pnl_pct for t in self._losers() if t.pnl_pct is not None)
        )
        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def average_hold_time(self) -> float:
        hold_bars = [t.hold_bars for t in self.trades if t.hold_bars is not None]
        return sum(hold_bars) / len(hold_bars) if hold_bars else 0.0

    def time_in_market(self) -> float:
        if not self.trades:
            return 0.0
        total_hold_bars = sum(
            t.hold_bars for t in self.trades if t.hold_bars is not None
        )
        total_bars = self._bar_range()
        return (total_hold_bars / total_bars) if total_bars > 0 else 0.0

    def capital_usage(self) -> float:
        if not self.trades:
            return 0.0
        avg_hold = self.average_hold_time()
        total_bars = self._bar_range()
        if total_bars == 0:
            return 0.0
        return avg_hold / total_bars if total_bars > 0 else 0.0

    def compute_time_horizon_distributions(self) -> TimeHorizonDistribution:
        monthly = self._compute_monthly_distribution()
        quarterly = self._compute_quarterly_distribution()
        yearly = self._compute_yearly_distribution()
        return TimeHorizonDistribution(
            monthly=monthly, quarterly=quarterly, yearly=yearly
        )

    def _winners(self) -> list[Trade]:
        return [t for t in self.trades if t.pnl_pct is not None and t.pnl_pct > 0]

    def _losers(self) -> list[Trade]:
        return [t for t in self.trades if t.pnl_pct is not None and t.pnl_pct <= 0]

    def _bar_range(self) -> int:
        bars = [t.exit_bar for t in self.trades if t.exit_bar is not None]
        if not bars:
            return 0
        return max(bars) - min(bars) + 1 if bars else 0

    def _compute_monthly_distribution(self) -> dict[str, float]:
        monthly_pnl: dict[str, float] = {}
        for trade in self.trades:
            if trade.exit_bar is None or trade.pnl_pct is None:
                continue
            month_key = f"M{trade.exit_bar // 20}"
            monthly_pnl[month_key] = monthly_pnl.get(month_key, 0.0) + trade.pnl_pct
        return monthly_pnl

    def _compute_quarterly_distribution(self) -> dict[str, float]:
        quarterly_pnl: dict[str, float] = {}
        for trade in self.trades:
            if trade.exit_bar is None or trade.pnl_pct is None:
                continue
            quarter_key = f"Q{trade.exit_bar // 60}"
            quarterly_pnl[quarter_key] = (
                quarterly_pnl.get(quarter_key, 0.0) + trade.pnl_pct
            )
        return quarterly_pnl

    def _compute_yearly_distribution(self) -> dict[str, float]:
        yearly_pnl: dict[str, float] = {}
        for trade in self.trades:
            if trade.exit_bar is None or trade.pnl_pct is None:
                continue
            year_key = f"Y{trade.exit_bar // 240}"
            yearly_pnl[year_key] = yearly_pnl.get(year_key, 0.0) + trade.pnl_pct
        return yearly_pnl


def compute_metrics(result: BacktestResult) -> dict:
    calculator = MetricsCalculator(result)
    return calculator.compute_all()


def compute_distributions(result: BacktestResult) -> TimeHorizonDistribution:
    calculator = MetricsCalculator(result)
    return calculator.compute_time_horizon_distributions()
