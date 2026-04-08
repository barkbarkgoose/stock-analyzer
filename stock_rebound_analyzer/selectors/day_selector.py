from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Iterable

from ..data import CachedDataProvider
from ..data_providers import get_provider
from ..data_providers.base import DataProvider
from ..models import DailyBar


class DayType(str, Enum):
    IMMEDIATE_REBOUND = "immediate_rebound"
    CONTINUED_SELLOFF = "continued_selloff"
    CHOPPY_REVERSAL = "choppy_reversal"
    GAP_DOWN_RECOVERY = "gap_down_recovery"
    TREND_DOWN_FAILURE = "trend_down_failure"
    NORMAL = "normal"


@dataclass(frozen=True)
class QualifyingDay:
    date: date
    day_type: DayType
    dip_pct: float
    recovery_pct: float
    watch_triggered: bool


@dataclass
class DaySelectionConfig:
    dip_threshold_pct: float
    day_types: set[DayType] | None = None
    include_normal_days: bool = False
    volatility_filter: str = "all"
    volatility_lookback_days: int = 20
    high_volatility_range_multiplier: float = 1.5

    def __post_init__(self) -> None:
        self.dip_threshold_pct = _normalize_pct(self.dip_threshold_pct)
        if self.dip_threshold_pct <= 0:
            raise ValueError("dip_threshold_pct must be > 0")
        if self.volatility_filter not in {"all", "normal", "high"}:
            raise ValueError("volatility_filter must be one of: all, normal, high")
        if self.volatility_lookback_days <= 0:
            raise ValueError("volatility_lookback_days must be > 0")
        if self.high_volatility_range_multiplier <= 0:
            raise ValueError("high_volatility_range_multiplier must be > 0")
        if self.day_types is not None:
            self.day_types = {_coerce_day_type(day_type) for day_type in self.day_types}

    @classmethod
    def from_any(cls, config: DaySelectionConfig | Any) -> DaySelectionConfig:
        if isinstance(config, cls):
            return config
        if config is None:
            raise ValueError("config is required")

        dip_threshold_pct = getattr(
            config,
            "dip_threshold_pct",
            getattr(config, "min_dip_threshold_pct", None),
        )
        if dip_threshold_pct is None:
            raise ValueError("config must define dip_threshold_pct or min_dip_threshold_pct")

        raw_day_types = getattr(
            config,
            "day_types",
            getattr(config, "allowed_day_types", None),
        )
        day_types = None
        if raw_day_types is not None:
            day_types = {_coerce_day_type(day_type) for day_type in raw_day_types}

        return cls(
            dip_threshold_pct=dip_threshold_pct,
            day_types=day_types,
            include_normal_days=getattr(config, "include_normal_days", False),
            volatility_filter=getattr(config, "volatility_filter", "all"),
            volatility_lookback_days=getattr(config, "volatility_lookback_days", 20),
            high_volatility_range_multiplier=getattr(
                config,
                "high_volatility_range_multiplier",
                1.5,
            ),
        )


class DayClassifier:
    def classify_days(
        self,
        bars: list[DailyBar],
        config: DaySelectionConfig | Any,
    ) -> list[QualifyingDay]:
        selection_config = DaySelectionConfig.from_any(config)
        qualifying_days: list[QualifyingDay] = []

        for index in range(1, len(bars)):
            qualifying_day = self.classify_day(bars, index=index, config=selection_config)
            is_high_volatility = _is_high_volatility_day(
                bars,
                index=index,
                config=selection_config,
            )
            if self._should_include(
                qualifying_day,
                is_high_volatility=is_high_volatility,
                config=selection_config,
            ):
                qualifying_days.append(qualifying_day)

        return qualifying_days

    def classify_day(
        self,
        bars: list[DailyBar],
        index: int,
        config: DaySelectionConfig | Any,
    ) -> QualifyingDay:
        selection_config = DaySelectionConfig.from_any(config)
        previous_bar = bars[index - 1]
        current_bar = bars[index]
        next_bar = bars[index + 1] if index + 1 < len(bars) else None

        previous_close = previous_bar.close
        if previous_close <= 0 or current_bar.low <= 0:
            return QualifyingDay(
                date=current_bar.date,
                day_type=DayType.NORMAL,
                dip_pct=0.0,
                recovery_pct=0.0,
                watch_triggered=False,
            )

        dip_pct = max((previous_close - current_bar.low) / previous_close, 0.0)
        close_dip_pct = max((previous_close - current_bar.close) / previous_close, 0.0)
        recovery_pct = max((current_bar.close - current_bar.low) / current_bar.low, 0.0)
        watch_triggered = (
            dip_pct >= selection_config.dip_threshold_pct
            or close_dip_pct >= selection_config.dip_threshold_pct
        )

        day_type = _classify_day_type(
            previous_close=previous_close,
            current_bar=current_bar,
            next_bar=next_bar,
            dip_pct=dip_pct,
            close_dip_pct=close_dip_pct,
            recovery_pct=recovery_pct,
            watch_triggered=watch_triggered,
            dip_threshold_pct=selection_config.dip_threshold_pct,
        )

        return QualifyingDay(
            date=current_bar.date,
            day_type=day_type,
            dip_pct=dip_pct,
            recovery_pct=recovery_pct,
            watch_triggered=watch_triggered,
        )

    def _should_include(
        self,
        qualifying_day: QualifyingDay,
        *,
        is_high_volatility: bool,
        config: DaySelectionConfig,
    ) -> bool:
        if config.day_types is not None and qualifying_day.day_type not in config.day_types:
            return False
        if not _matches_volatility_filter(
            is_high_volatility=is_high_volatility,
            volatility_filter=config.volatility_filter,
        ):
            return False
        if qualifying_day.watch_triggered:
            return True
        return config.include_normal_days or (
            config.day_types is not None and DayType.NORMAL in config.day_types
        )


class DaySelector:
    def __init__(self, provider: DataProvider | None = None) -> None:
        self.provider = provider
        self.classifier = DayClassifier()

    def select_qualifying_days(
        self,
        symbol: str,
        start: str,
        end: str,
        config: DaySelectionConfig | Any,
    ) -> list[QualifyingDay]:
        provider = self._resolve_provider()
        bars = provider.fetch_daily_bars(symbol=symbol, start=start, end=end)
        return self.classifier.classify_days(bars=bars, config=config)

    def _resolve_provider(self) -> DataProvider:
        if self.provider is not None:
            return self.provider

        data_source = os.getenv("DATA_SOURCE", "yahoo")
        return CachedDataProvider(get_provider(data_source))


def _classify_day_type(
    *,
    previous_close: float,
    current_bar: DailyBar,
    next_bar: DailyBar | None,
    dip_pct: float,
    close_dip_pct: float,
    recovery_pct: float,
    watch_triggered: bool,
    dip_threshold_pct: float,
) -> DayType:
    if not watch_triggered:
        return DayType.NORMAL

    range_size = max(current_bar.high - current_bar.low, 0.0)
    close_position = (
        (current_bar.close - current_bar.low) / range_size if range_size > 0 else 0.5
    )
    gap_down_pct = max((previous_close - current_bar.open) / previous_close, 0.0)
    retracement_ratio = 0.0
    lost_range = previous_close - current_bar.low
    if lost_range > 0:
        retracement_ratio = (current_bar.close - current_bar.low) / lost_range

    next_close_change_pct = 0.0
    next_low_break = False
    next_failed_bounce = False
    if next_bar is not None and current_bar.close > 0:
        next_close_change_pct = (next_bar.close - current_bar.close) / current_bar.close
        next_low_break = next_bar.low < current_bar.low
        next_failed_bounce = next_bar.high > current_bar.close * 1.01 and next_bar.close < current_bar.close

    if (
        gap_down_pct >= dip_threshold_pct * 0.6
        and current_bar.close >= current_bar.open
        and close_position >= 0.65
        and retracement_ratio >= 0.5
    ):
        return DayType.GAP_DOWN_RECOVERY

    if (
        close_position >= 0.75
        and close_dip_pct <= dip_threshold_pct * 0.5
        and retracement_ratio >= 0.6
    ):
        return DayType.IMMEDIATE_REBOUND

    if (
        close_position <= 0.25
        and close_dip_pct >= dip_threshold_pct * 0.8
    ) or (
        next_low_break
        and next_close_change_pct < -(dip_threshold_pct * 0.25)
        and retracement_ratio < 0.35
    ):
        return DayType.CONTINUED_SELLOFF

    if (
        next_failed_bounce
        and retracement_ratio >= 0.25
    ) or (
        current_bar.close < current_bar.open
        and close_position < 0.55
        and retracement_ratio >= 0.25
        and recovery_pct > 0
    ):
        return DayType.TREND_DOWN_FAILURE

    return DayType.CHOPPY_REVERSAL


def _is_high_volatility_day(
    bars: list[DailyBar],
    *,
    index: int,
    config: DaySelectionConfig,
) -> bool:
    current_range_pct = _daily_range_pct(bars[index - 1].close, bars[index])
    lookback_start = max(1, index - config.volatility_lookback_days)
    trailing_ranges = [
        _daily_range_pct(bars[position - 1].close, bars[position])
        for position in range(lookback_start, index)
    ]
    baseline_range_pct = _mean(trailing_ranges)

    if baseline_range_pct <= 0:
        return current_range_pct >= config.dip_threshold_pct

    return current_range_pct >= (
        baseline_range_pct * config.high_volatility_range_multiplier
    )


def _daily_range_pct(previous_close: float, current_bar: DailyBar) -> float:
    if previous_close <= 0:
        return 0.0
    return max((current_bar.high - current_bar.low) / previous_close, 0.0)


def _matches_volatility_filter(*, is_high_volatility: bool, volatility_filter: str) -> bool:
    if volatility_filter == "all":
        return True
    if volatility_filter == "high":
        return is_high_volatility
    return not is_high_volatility


def _coerce_day_type(value: DayType | str) -> DayType:
    if isinstance(value, DayType):
        return value
    return DayType(value)


def _mean(values: Iterable[float]) -> float:
    sequence = list(values)
    if not sequence:
        return 0.0
    return sum(sequence) / len(sequence)


def _normalize_pct(value: float) -> float:
    return value / 100 if value > 1 else value


__all__ = [
    "DayClassifier",
    "DaySelectionConfig",
    "DaySelector",
    "DayType",
    "QualifyingDay",
]
