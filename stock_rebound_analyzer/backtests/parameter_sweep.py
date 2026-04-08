from dataclasses import dataclass, field
from itertools import product
from typing import Callable, Optional

from .state_machine import BacktestResult, StateMachineBacktester, StrategyConfig


@dataclass
class ParameterGrid:
    trigger_drop_thresholds: list[float] = field(
        default_factory=lambda: [2.0, 3.0, 4.0]
    )
    rebound_confirmation_thresholds: list[float] = field(
        default_factory=lambda: [0.5, 1.0, 1.5]
    )
    profit_targets: list[float] = field(default_factory=lambda: [1.0, 2.0, 3.0])
    stop_losses: list[float] = field(default_factory=lambda: [1.0, 1.5, 2.0])
    cooldown_periods: list[int] = field(default_factory=lambda: [0, 3, 5])
    anchor_names: list[str] = field(default_factory=lambda: ["previous_close"])
    time_stops: list[int] = field(default_factory=lambda: [10, 20, 30])
    bar_granularities: list[str] = field(default_factory=lambda: ["5min"])

    def iter_combinations(self) -> list[dict]:
        keys = [
            "trigger_drop_thresholds",
            "rebound_confirmation_thresholds",
            "profit_targets",
            "stop_losses",
            "cooldown_periods",
            "anchor_names",
            "time_stops",
            "bar_granularities",
        ]
        values = [
            self.trigger_drop_thresholds,
            self.rebound_confirmation_thresholds,
            self.profit_targets,
            self.stop_losses,
            self.cooldown_periods,
            self.anchor_names,
            self.time_stops,
            self.bar_granularities,
        ]
        combinations = []
        for combo in product(*values):
            combinations.append(dict(zip(keys, combo)))
        return combinations


@dataclass
class SweepResult:
    params: dict
    result: BacktestResult
    param_signature: str = ""

    def __post_init__(self):
        self.param_signature = self._make_signature(self.params)

    @staticmethod
    def _make_signature(params: dict) -> str:
        parts = []
        for k, v in sorted(params.items()):
            short_k = k.replace("trigger_drop_thresholds", "drop")
            short_k = short_k.replace("rebound_confirmation_thresholds", "rebound")
            short_k = short_k.replace("profit_targets", "pt")
            short_k = short_k.replace("stop_losses", "sl")
            short_k = short_k.replace("cooldown_periods", "cd")
            short_k = short_k.replace("anchor_names", "anchor")
            short_k = short_k.replace("time_stops", "ts")
            short_k = short_k.replace("bar_granularities", "gran")
            parts.append(f"{short_k}={v}")
        return ", ".join(parts)


class ParameterSweep:
    def __init__(
        self, bars_loader: Optional[Callable[[str, str, str, str], list]] = None
    ):
        self._bars_loader = bars_loader

    def run(
        self,
        symbol: str,
        start: str,
        end: str,
        grid: ParameterGrid,
        bar_granularity: str = "5min",
    ) -> list[SweepResult]:
        results = []
        combinations = grid.iter_combinations()

        for params in combinations:
            config = StrategyConfig(
                drop_threshold_pct=params["trigger_drop_thresholds"],
                rebound_confirmation_pct=params["rebound_confirmation_thresholds"],
                profit_target_pct=params["profit_targets"],
                stop_loss_pct=params["stop_losses"],
                cooldown_bars=params["cooldown_periods"],
                cooldown_minutes=0,
                max_holding_bars=params["time_stops"],
                end_of_day_exit=True,
                anchor_name=params["anchor_names"],
            )

            backtester = StateMachineBacktester(config)

            bars = self._load_bars(symbol, start, end, params["bar_granularities"])
            result = backtester.run(bars)

            sweep_result = SweepResult(params=params, result=result)
            results.append(sweep_result)

        return results

    def _load_bars(self, symbol: str, start: str, end: str, granularity: str) -> list:
        if self._bars_loader is not None:
            return self._bars_loader(symbol, start, end, granularity)
        raise NotImplementedError(
            "No bars_loader provided. Provide a bars_loader function to load data."
        )


@dataclass
class AggregationProfile:
    name: str
    description: str
    metric_weights: dict

    def score(self, metrics: dict) -> float:
        score = 0.0
        for metric, weight in self.metric_weights.items():
            if metric in metrics:
                score += metrics[metric] * weight
        return score


FREQ_SMALL_INCOME = AggregationProfile(
    name="frequent_small_income",
    description="Favors high trade frequency with smaller but consistent profits",
    metric_weights={
        "total_trades": 0.4,
        "win_rate": 0.3,
        "average_pnl_pct": 0.2,
        "max_drawdown_pct": -0.1,
    },
)

SMOOTHER_COMPOUNDING = AggregationProfile(
    name="smoother_longer_term_compounding",
    description="Balanced approach favoring steady compounding with lower drawdown",
    metric_weights={
        "win_rate": 0.3,
        "average_pnl_pct": 0.25,
        "max_drawdown_pct": -0.3,
        "average_hold_bars": 0.15,
    },
)

BEST_RISK_ADJUSTED = AggregationProfile(
    name="best_risk_adjusted",
    description="Prioritizes risk-adjusted returns and drawdown protection",
    metric_weights={
        "win_rate": 0.35,
        "average_pnl_pct": 0.25,
        "max_drawdown_pct": -0.4,
    },
)


class ResultAggregator:
    def __init__(self, results: list[SweepResult]):
        self.results = results

    def get_best(self, profile: AggregationProfile) -> SweepResult:
        best = None
        best_score = float("-inf")
        for result in self.results:
            if result.result.metrics["total_trades"] == 0:
                continue
            score = profile.score(result.result.metrics)
            if score > best_score:
                best_score = score
                best = result
        if best is None:
            return self.results[0]
        return best

    def get_top_n(self, profile: AggregationProfile, n: int) -> list[SweepResult]:
        scored = []
        for result in self.results:
            if result.result.metrics["total_trades"] == 0:
                continue
            score = profile.score(result.result.metrics)
            scored.append((score, result))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:n]]

    def get_summary_table(self) -> list[dict]:
        table = []
        for result in self.results:
            row = {
                "signature": result.param_signature,
                "total_trades": result.result.metrics["total_trades"],
                "win_rate": f"{result.result.metrics['win_rate']:.2%}",
                "avg_pnl": f"{result.result.metrics['average_pnl_pct']:.3f}%",
                "max_gain": f"{result.result.metrics['max_gain_pct']:.3f}%",
                "max_loss": f"{result.result.metrics['max_drawdown_pct']:.3f}%",
                "avg_hold_bars": f"{result.result.metrics['average_hold_bars']:.1f}",
            }
            table.append(row)
        return table
