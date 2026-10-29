"""Configuration for a symbol profile / signal study."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, fields, replace
from typing import Any

from .types import TIMEFRAME_MINUTES, SUPPORTED_TIMEFRAMES


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Parameters for the dip/rebound event study and trade simulation.

    The defaults are deliberately conservative: buy only after a dip, wait for
    confirmation, take 1% before a 2% stop, and do not hold for more than two
    trading days.
    """

    timeframe: str = "5m"
    dip_threshold_pct: float = 5.0
    dip_lookback_days: float = 2.0
    target_pct: float = 1.0
    stop_pct: float = 2.0
    stop_mode: str = "fixed"  # fixed | episode_low
    stop_buffer_pct: float = 0.25
    min_stop_pct: float = 0.75
    max_stop_pct: float = 4.0
    max_hold_days: float = 2.0
    fast_horizon_minutes: int = 120
    max_runup_from_low_pct: float = 3.0

    attempt_min_pct: float = 0.4
    episode_max_days: float = 10.0
    swing_pivot_bars: int = 2

    entry_slippage_bps: float = 5.0
    exit_slippage_bps: float = 5.0
    commission_bps: float = 0.0

    exclude_first_minutes: int = 15
    exclude_last_minutes: int = 15
    only_uptrend_signals: bool = False
    uptrend_min_score: float = 0.5

    # Qualification thresholds (daily data).
    min_daily_bars: int = 120
    min_intraday_bars: int = 180
    min_price: float = 5.0
    min_dollar_volume: float = 20_000_000.0
    volatility_lookback_days: int = 60
    volatility_min_range_days: int = 3
    volatility_min_atr_pct: float = 3.0
    max_distance_from_sma50_pct: float = 30.0
    max_below_sma50_pct: float = 5.0
    max_drawdown_1y_pct: float = 55.0
    uptrend_min_6m_return_pct: float = 0.0
    uptrend_require_sma200: bool = True
    uptrend_require_sma50_gt_sma200: bool = True
    daily_recovery_target_pct: float = 5.0
    daily_recovery_window_days: int = 10

    # Model / rule selection.
    min_samples_for_model: int = 40
    model_threshold: float = 0.5
    walk_forward_folds: int = 4
    min_trades_for_rule: int = 5
    min_trades_for_threshold: int = 8
    enabled_rules: tuple[str, ...] | None = None

    # Data acquisition (used by the Django service; kept here so the config hash
    # captures the whole study).
    daily_history_days: int = 1100
    intraday_history_days: int = 60

    def __post_init__(self) -> None:
        if self.timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"timeframe must be one of {', '.join(SUPPORTED_TIMEFRAMES)}"
            )
        if self.dip_threshold_pct <= 0:
            raise ValueError("dip_threshold_pct must be > 0")
        if self.target_pct <= 0:
            raise ValueError("target_pct must be > 0")
        if self.stop_pct <= 0:
            raise ValueError("stop_pct must be > 0")
        if self.max_hold_days <= 0:
            raise ValueError("max_hold_days must be > 0")
        if self.stop_mode not in {"fixed", "episode_low"}:
            raise ValueError("stop_mode must be 'fixed' or 'episode_low'")
        if self.stop_buffer_pct < 0:
            raise ValueError("stop_buffer_pct must be >= 0")
        if self.max_stop_pct < self.min_stop_pct:
            raise ValueError("max_stop_pct must be >= min_stop_pct")
        if self.dip_lookback_days <= 0:
            raise ValueError("dip_lookback_days must be > 0")
        if self.fast_horizon_minutes <= 0:
            raise ValueError("fast_horizon_minutes must be > 0")
        if self.max_runup_from_low_pct <= 0:
            raise ValueError("max_runup_from_low_pct must be > 0")
        if self.attempt_min_pct <= 0:
            raise ValueError("attempt_min_pct must be > 0")
        if self.episode_max_days <= 0:
            raise ValueError("episode_max_days must be > 0")
        if self.swing_pivot_bars < 1:
            raise ValueError("swing_pivot_bars must be >= 1")
        if self.walk_forward_folds < 2:
            raise ValueError("walk_forward_folds must be >= 2")

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------
    @property
    def minutes_per_bar(self) -> int | None:
        return TIMEFRAME_MINUTES[self.timeframe]

    @property
    def is_intraday(self) -> bool:
        return self.timeframe != "1d"

    @property
    def bars_per_day(self) -> int:
        minutes = self.minutes_per_bar
        if minutes is None:
            return 1
        return max(1, math.ceil(390 / minutes))

    @property
    def dip_lookback_bars(self) -> int:
        return max(2, round(self.dip_lookback_days * self.bars_per_day))

    @property
    def max_hold_bars(self) -> int:
        return max(1, round(self.max_hold_days * self.bars_per_day))

    @property
    def fast_horizon_bars(self) -> int:
        minutes = self.minutes_per_bar
        if minutes is None:
            return 1
        return max(1, round(self.fast_horizon_minutes / minutes))

    @property
    def episode_max_bars(self) -> int:
        return max(self.dip_lookback_bars, round(self.episode_max_days * self.bars_per_day))

    @property
    def total_cost_bps(self) -> float:
        return self.entry_slippage_bps + self.exit_slippage_bps + self.commission_bps

    @property
    def fast_horizon_label(self) -> str:
        if self.timeframe == "1d":
            return "next trading day"
        if self.fast_horizon_minutes % 60 == 0:
            return f"{self.fast_horizon_minutes // 60}h"
        return f"{self.fast_horizon_minutes}m"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("enabled_rules") is not None:
            data["enabled_rules"] = list(data["enabled_rules"])
        return data

    @property
    def hash(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AnalysisConfig":
        if not data:
            return cls()
        allowed = {f.name for f in fields(cls)}
        clean: dict[str, Any] = {}
        for key, value in data.items():
            if key not in allowed or value is None:
                continue
            clean[key] = value
        if "enabled_rules" in clean and isinstance(clean["enabled_rules"], list):
            clean["enabled_rules"] = tuple(str(v) for v in clean["enabled_rules"])
        if "timeframe" in clean:
            clean["timeframe"] = str(clean["timeframe"]).lower()
        return cls(**clean)

    def with_overrides(self, **overrides: Any) -> "AnalysisConfig":
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean)


def config_schema() -> dict[str, Any]:
    """Small JSON-schema-ish description for the UI.

    This is intentionally hand-written rather than generated: it groups the
    knobs into concepts a trader cares about (dip, entry, risk, universe) and
    keeps the frontend from guessing defaults.
    """

    return {
        "sections": [
            {
                "id": "signal",
                "label": "Signal",
                "fields": [
                    {"key": "timeframe", "label": "Signal timeframe", "type": "select", "options": ["1m", "5m", "15m", "30m", "1h", "1d"]},
                    {"key": "dip_threshold_pct", "label": "Dip threshold %", "type": "number", "min": 1, "max": 30, "step": 0.5},
                    {"key": "dip_lookback_days", "label": "Dip lookback (days)", "type": "number", "min": 0.25, "max": 10, "step": 0.25},
                    {"key": "fast_horizon_minutes", "label": "Fast horizon (minutes)", "type": "number", "min": 15, "max": 390, "step": 15},
                    {"key": "max_runup_from_low_pct", "label": "Max run-up from low %", "type": "number", "min": 0.5, "max": 15, "step": 0.5},
                ],
            },
            {
                "id": "trade",
                "label": "Trade",
                "fields": [
                    {"key": "target_pct", "label": "Target %", "type": "number", "min": 0.25, "max": 10, "step": 0.25},
                    {"key": "stop_pct", "label": "Fixed stop %", "type": "number", "min": 0.5, "max": 10, "step": 0.25},
                    {"key": "stop_mode", "label": "Stop mode", "type": "select", "options": ["fixed", "episode_low"]},
                    {"key": "max_hold_days", "label": "Max hold (trading days)", "type": "number", "min": 0.5, "max": 20, "step": 0.5},
                ],
            },
            {
                "id": "costs",
                "label": "Costs",
                "fields": [
                    {"key": "entry_slippage_bps", "label": "Entry slippage (bps)", "type": "number", "min": 0, "max": 100, "step": 1},
                    {"key": "exit_slippage_bps", "label": "Exit slippage (bps)", "type": "number", "min": 0, "max": 100, "step": 1},
                    {"key": "commission_bps", "label": "Commission (bps/side)", "type": "number", "min": 0, "max": 100, "step": 1},
                ],
            },
            {
                "id": "filters",
                "label": "Filters",
                "fields": [
                    {"key": "exclude_first_minutes", "label": "Skip first (min)", "type": "number", "min": 0, "max": 120, "step": 5},
                    {"key": "exclude_last_minutes", "label": "Skip last (min)", "type": "number", "min": 0, "max": 120, "step": 5},
                    {"key": "only_uptrend_signals", "label": "Only uptrend signals", "type": "boolean"},
                    {"key": "uptrend_min_score", "label": "Min uptrend score", "type": "number", "min": 0, "max": 1, "step": 0.1},
                ],
            },
        ]
    }
