from __future__ import annotations

import os
import statistics
from dataclasses import dataclass, field
from typing import Any

from ..analysis import analyze_dip_rebounds
from ..data import CachedDataProvider
from ..data_providers import get_provider
from ..data_providers.base import DataProvider
from ..models import AnalysisReport, DailyBar


_DEFAULT_SCORING_WEIGHTS = {
    "drop_frequency": 0.2,
    "rebound_behavior": 0.25,
    "consistency": 0.15,
    "drawdown": 0.15,
    "volatility": 0.1,
    "setup_frequency": 0.15,
}


@dataclass(frozen=True)
class StockProfile:
    symbol: str
    date_range: tuple[str, str]
    total_bars: int
    dip_count: int
    dip_frequency: dict[str, float]
    average_dip_pct: float
    average_rebound_pct: float
    volatility_profile: dict[str, float]
    worst_drawdown: float


@dataclass
class ScanConfig:
    min_dip_threshold_pct: float
    min_dips_per_month: float
    max_dips_per_week: float
    liquidity_filter: float | None = None
    volatility_range: tuple[float | None, float | None] = (None, None)
    rebound_target_pct: float = 0.03
    rebound_window_days: int = 5
    minimum_history_bars: int = 30
    scoring_weights: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_SCORING_WEIGHTS)
    )

    def __post_init__(self) -> None:
        self.min_dip_threshold_pct = _normalize_pct(self.min_dip_threshold_pct)
        self.rebound_target_pct = _normalize_pct(self.rebound_target_pct)

        if self.min_dip_threshold_pct <= 0:
            raise ValueError("min_dip_threshold_pct must be > 0")
        if self.min_dips_per_month < 0:
            raise ValueError("min_dips_per_month must be >= 0")
        if self.max_dips_per_week < 0:
            raise ValueError("max_dips_per_week must be >= 0")
        if self.rebound_target_pct <= 0:
            raise ValueError("rebound_target_pct must be > 0")
        if self.rebound_window_days <= 0:
            raise ValueError("rebound_window_days must be > 0")
        if self.minimum_history_bars < 2:
            raise ValueError("minimum_history_bars must be >= 2")
        if self.liquidity_filter is not None and self.liquidity_filter < 0:
            raise ValueError("liquidity_filter must be >= 0")

        minimum_volatility, maximum_volatility = self.volatility_range
        if (
            minimum_volatility is not None
            and maximum_volatility is not None
            and minimum_volatility > maximum_volatility
        ):
            raise ValueError("volatility_range minimum cannot exceed maximum")

        total_weight = sum(self.scoring_weights.values())
        if total_weight <= 0:
            raise ValueError("scoring_weights must sum to a positive value")
        self.scoring_weights = {
            key: value / total_weight for key, value in self.scoring_weights.items()
        }


@dataclass(frozen=True)
class ScoredCandidate:
    symbol: str
    score: float
    breakdown: dict[str, Any]
    profile: StockProfile | None = None


class UniverseScanner:
    def __init__(self, provider: DataProvider | None = None) -> None:
        self.provider = provider

    def scan(
        self, symbols: list[str], start: str, end: str, config: ScanConfig
    ) -> list[ScoredCandidate]:
        provider = self._resolve_provider()
        candidates: list[ScoredCandidate] = []

        for raw_symbol in symbols:
            symbol = raw_symbol.upper().strip()
            if not symbol:
                continue

            try:
                bars = provider.fetch_daily_bars(symbol=symbol, start=start, end=end)
                candidate = self._score_symbol(symbol, start, end, bars, config)
            except Exception as exc:  # pragma: no cover - defensive fallback path
                candidate = ScoredCandidate(
                    symbol=symbol,
                    score=0.0,
                    breakdown={
                        "status": "error",
                        "reason": str(exc),
                        "component_scores": {},
                    },
                )
            candidates.append(candidate)

        return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.symbol))

    def _resolve_provider(self) -> DataProvider:
        if self.provider is not None:
            return self.provider

        data_source = os.getenv("DATA_SOURCE", "yahoo")
        return CachedDataProvider(get_provider(data_source))

    def _score_symbol(
        self,
        symbol: str,
        start: str,
        end: str,
        bars: list[DailyBar],
        config: ScanConfig,
    ) -> ScoredCandidate:
        if len(bars) < config.minimum_history_bars:
            return ScoredCandidate(
                symbol=symbol,
                score=0.0,
                breakdown={
                    "status": "insufficient_data",
                    "reason": (
                        f"Needed at least {config.minimum_history_bars} bars, found {len(bars)}"
                    ),
                    "component_scores": {},
                },
                profile=self._build_empty_profile(symbol, start, end, len(bars)),
            )

        report = analyze_dip_rebounds(
            symbol=symbol,
            bars=bars,
            dip_threshold_pct=config.min_dip_threshold_pct,
            rebound_target_pct=config.rebound_target_pct,
            rebound_window_days=config.rebound_window_days,
        )
        profile = self._build_profile(bars, report, start, end)
        scoring = self._calculate_scoring(bars, profile, report, config)

        return ScoredCandidate(
            symbol=symbol,
            score=scoring["score"],
            breakdown=scoring["breakdown"],
            profile=profile,
        )

    def _build_empty_profile(
        self, symbol: str, start: str, end: str, total_bars: int
    ) -> StockProfile:
        return StockProfile(
            symbol=symbol,
            date_range=(start, end),
            total_bars=total_bars,
            dip_count=0,
            dip_frequency={"per_week": 0.0, "per_month": 0.0},
            average_dip_pct=0.0,
            average_rebound_pct=0.0,
            volatility_profile={
                "daily_std_pct": 0.0,
                "annualized_std_pct": 0.0,
                "average_daily_range_pct": 0.0,
            },
            worst_drawdown=0.0,
        )

    def _build_profile(
        self,
        bars: list[DailyBar],
        report: AnalysisReport,
        requested_start: str,
        requested_end: str,
    ) -> StockProfile:
        dip_events = report.dip_events
        average_dip_pct = _mean(event.dip_pct for event in dip_events)
        average_rebound_pct = _mean(event.max_return_pct for event in dip_events)
        volatility_profile = _calculate_volatility_profile(bars)
        worst_drawdown = _calculate_peak_to_trough_drawdown(bars)

        total_bars = len(bars)
        weeks = total_bars / 5 if total_bars else 0.0
        months = total_bars / 21 if total_bars else 0.0
        dip_frequency = {
            "per_week": report.dip_count / weeks if weeks else 0.0,
            "per_month": report.dip_count / months if months else 0.0,
        }

        actual_start = bars[0].date.isoformat() if bars else requested_start
        actual_end = bars[-1].date.isoformat() if bars else requested_end

        return StockProfile(
            symbol=report.symbol,
            date_range=(actual_start, actual_end),
            total_bars=total_bars,
            dip_count=report.dip_count,
            dip_frequency=dip_frequency,
            average_dip_pct=average_dip_pct,
            average_rebound_pct=average_rebound_pct,
            volatility_profile=volatility_profile,
            worst_drawdown=worst_drawdown,
        )

    def _calculate_scoring(
        self,
        bars: list[DailyBar],
        profile: StockProfile,
        report: AnalysisReport,
        config: ScanConfig,
    ) -> dict[str, Any]:
        return _score_profile(bars, profile, report, config)


# The implementation below is attached after the class to keep helper signatures small.
def _score_profile(
    bars: list[DailyBar],
    profile: StockProfile,
    report: AnalysisReport,
    config: ScanConfig,
) -> dict[str, Any]:
    avg_dollar_volume = _mean(bar.close * bar.volume for bar in bars)
    dip_events = report.dip_events
    completed_events = [event for event in dip_events if event.window_complete]

    dips_per_month = profile.dip_frequency["per_month"]
    dips_per_week = profile.dip_frequency["per_week"]

    if config.min_dips_per_month == 0:
        monthly_progress = 1.0
    else:
        monthly_progress = min(dips_per_month / config.min_dips_per_month, 1.0)
    if config.max_dips_per_week > 0:
        weekly_ratio = dips_per_week / config.max_dips_per_week
        weekly_penalty = min(max(weekly_ratio - 1.0, 0.0), 1.0)
        drop_frequency = max(0.0, monthly_progress * (1.0 - weekly_penalty))
    else:
        drop_frequency = monthly_progress if dips_per_week == 0 else 0.0

    rebound_target = max(config.rebound_target_pct, 1e-9)
    rebound_strength = min(profile.average_rebound_pct / rebound_target, 1.0)
    rebound_behavior = (report.success_rate * 0.7) + (rebound_strength * 0.3)

    completed_rebounds = [event.max_return_pct for event in completed_events]
    if len(completed_rebounds) >= 2:
        rebound_stdev = statistics.pstdev(completed_rebounds)
        consistency = max(0.0, 1.0 - (rebound_stdev / max(profile.average_rebound_pct, 1e-9)))
    elif completed_rebounds:
        rebound_stdev = 0.0
        consistency = 1.0
    else:
        rebound_stdev = 0.0
        consistency = 0.0

    avg_completed_drawdown = _mean(event.worst_drawdown_pct for event in completed_events)
    drawdown_penalty = min(abs(avg_completed_drawdown) / max(config.min_dip_threshold_pct, 1e-9), 1.0)
    worst_penalty = min(abs(profile.worst_drawdown) / 0.35, 1.0)
    drawdown = max(0.0, 1.0 - ((drawdown_penalty * 0.6) + (worst_penalty * 0.4)))

    annualized_volatility = profile.volatility_profile["annualized_std_pct"]
    volatility = _score_volatility(annualized_volatility, config.volatility_range)

    week_coverage = _unique_bucket_ratio(dip_events, bucket="week", total_bars=profile.total_bars)
    month_coverage = _unique_bucket_ratio(dip_events, bucket="month", total_bars=profile.total_bars)
    setup_frequency = (week_coverage * 0.4) + (month_coverage * 0.6)

    component_scores = {
        "drop_frequency": round(drop_frequency, 4),
        "rebound_behavior": round(rebound_behavior, 4),
        "consistency": round(consistency, 4),
        "drawdown": round(drawdown, 4),
        "volatility": round(volatility, 4),
        "setup_frequency": round(setup_frequency, 4),
    }

    weighted_score = 0.0
    for key, component_score in component_scores.items():
        weighted_score += component_score * config.scoring_weights.get(key, 0.0)

    flags: list[str] = []
    if dips_per_month < config.min_dips_per_month:
        flags.append("below_min_dips_per_month")
    if config.max_dips_per_week > 0 and dips_per_week > config.max_dips_per_week:
        flags.append("above_max_dips_per_week")
    if config.liquidity_filter is not None and avg_dollar_volume < config.liquidity_filter:
        flags.append("below_liquidity_filter")
    minimum_volatility, maximum_volatility = config.volatility_range
    if minimum_volatility is not None and annualized_volatility < minimum_volatility:
        flags.append("below_min_volatility")
    if maximum_volatility is not None and annualized_volatility > maximum_volatility:
        flags.append("above_max_volatility")

    eligible = not flags
    final_score = round(weighted_score * 100 if eligible else weighted_score * 50, 2)

    notes = [
        (
            f"{report.dip_count} dips over {profile.total_bars} bars "
            f"({dips_per_week:.2f}/week, {dips_per_month:.2f}/month)."
        ),
        (
            f"Resolved rebound success rate {report.success_rate:.1%} with "
            f"average rebound {profile.average_rebound_pct:.1%}."
        ),
        (
            f"Annualized volatility {annualized_volatility:.1%}; "
            f"worst price-series drawdown {profile.worst_drawdown:.1%}."
        ),
    ]
    if flags:
        notes.append("Filtered conditions: " + ", ".join(flags))

    return {
        "score": final_score,
        "breakdown": {
            "status": "ok" if eligible else "filtered",
            "eligible": eligible,
            "component_scores": component_scores,
            "metrics": {
                "dip_count": report.dip_count,
                "resolved_dip_count": report.resolved_dip_count,
                "success_rate": round(report.success_rate, 4),
                "average_dip_pct": round(profile.average_dip_pct, 4),
                "average_rebound_pct": round(profile.average_rebound_pct, 4),
                "average_post_dip_drawdown_pct": round(avg_completed_drawdown, 4),
                "worst_drawdown_pct": round(profile.worst_drawdown, 4),
                "annualized_volatility_pct": round(annualized_volatility, 4),
                "average_dollar_volume": round(avg_dollar_volume, 2),
                "setup_week_coverage": round(week_coverage, 4),
                "setup_month_coverage": round(month_coverage, 4),
                "rebound_stdev_pct": round(rebound_stdev, 4),
            },
            "flags": flags,
            "notes": notes,
        },
    }


def _normalize_pct(value: float) -> float:
    return value / 100 if value > 1 else value


def _mean(values: Any) -> float:
    sequence = list(values)
    if not sequence:
        return 0.0
    return sum(sequence) / len(sequence)


def _calculate_volatility_profile(bars: list[DailyBar]) -> dict[str, float]:
    close_returns: list[float] = []
    range_pcts: list[float] = []

    for idx, bar in enumerate(bars):
        if bar.close > 0:
            range_pcts.append((bar.high - bar.low) / bar.close)
        if idx == 0:
            continue
        previous_close = bars[idx - 1].close
        if previous_close <= 0:
            continue
        close_returns.append((bar.close - previous_close) / previous_close)

    daily_std = statistics.pstdev(close_returns) if len(close_returns) >= 2 else 0.0
    return {
        "daily_std_pct": daily_std,
        "annualized_std_pct": daily_std * (252 ** 0.5),
        "average_daily_range_pct": _mean(range_pcts),
    }


def _calculate_peak_to_trough_drawdown(bars: list[DailyBar]) -> float:
    peak = 0.0
    worst_drawdown = 0.0

    for bar in bars:
        if bar.close > peak:
            peak = bar.close
        if peak <= 0:
            continue
        drawdown = (bar.close - peak) / peak
        if drawdown < worst_drawdown:
            worst_drawdown = drawdown

    return worst_drawdown


def _score_volatility(
    annualized_volatility: float,
    volatility_range: tuple[float | None, float | None],
) -> float:
    minimum, maximum = volatility_range
    if minimum is None and maximum is None:
        return 1.0 if annualized_volatility > 0 else 0.0
    if minimum is not None and annualized_volatility < minimum:
        return max(0.0, annualized_volatility / max(minimum, 1e-9))
    if maximum is not None and annualized_volatility > maximum:
        overflow = annualized_volatility - maximum
        return max(0.0, 1.0 - (overflow / max(maximum, 1e-9)))
    return 1.0


def _unique_bucket_ratio(dip_events: list[Any], bucket: str, total_bars: int) -> float:
    if not dip_events or total_bars <= 0:
        return 0.0

    if bucket == "week":
        buckets = {(event.date.isocalendar().year, event.date.isocalendar().week) for event in dip_events}
        possible_buckets = max(total_bars / 5, 1.0)
    else:
        buckets = {(event.date.year, event.date.month) for event in dip_events}
        possible_buckets = max(total_bars / 21, 1.0)

    return min(len(buckets) / possible_buckets, 1.0)
