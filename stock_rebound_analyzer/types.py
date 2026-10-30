"""Shared domain types for the dip-rebound research engine.

The engine is deliberately independent of Django and of any data provider.  A
provider only has to produce :class:`Bar` objects; everything else (features,
signals, labels, statistics) is pure Python so it can be unit tested and reused
from the CLI, the API and background jobs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "1d"]
ExitReason = Literal["target", "stop", "timeout", "end_of_data"]
SignalSide = Literal["long"]

TIMEFRAME_MINUTES: dict[str, int | None] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "1d": None,
}

SUPPORTED_TIMEFRAMES = tuple(TIMEFRAME_MINUTES.keys())

# US regular session.  The providers are asked for regular-hours bars only, but
# synthetic fixtures and CSVs sometimes include pre/post data, so the session
# helpers clamp to this window.
SESSION_OPEN_MINUTES = 9 * 60 + 30
SESSION_CLOSE_MINUTES = 16 * 60
SESSION_MINUTES = SESSION_CLOSE_MINUTES - SESSION_OPEN_MINUTES


@dataclass(frozen=True, slots=True)
class Bar:
    """A single OHLCV bar.

    Timestamps are timezone-aware UTC.  Daily bars are normalised to midnight
    UTC for a stable unique key; intraday bars keep their exact timestamp.
    """

    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    timeframe: str = "1d"
    source: str = "unknown"

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None:
            raise ValueError("Bar.ts must be timezone-aware")
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise ValueError("Bar prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(
            self.open, self.close
        ):
            # Providers occasionally emit a bad tick.  We could raise, but a
            # research tool is more useful if it repairs the envelope and keeps
            # going.  The caller can see volume/price anomalies in the data
            # quality warnings.
            object.__setattr__(self, "high", max(self.open, self.close, self.high))
            object.__setattr__(self, "low", min(self.open, self.close, self.low))

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0

    @property
    def dollar_volume(self) -> float:
        return self.close * self.volume


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    """Result of entering at the next bar's open and using triple barriers."""

    entry_index: int
    entry_ts: datetime
    entry_price: float
    exit_index: int
    exit_ts: datetime
    exit_price: float
    return_pct: float
    net_return_pct: float
    mfe_pct: float
    mae_pct: float
    holding_bars: int
    holding_minutes: float
    holding_trading_minutes: float
    exit_reason: ExitReason
    success: bool
    fast_success: bool
    target_price: float
    stop_price: float

    @property
    def is_timeout(self) -> bool:
        return self.exit_reason == "timeout"

    @property
    def is_stop(self) -> bool:
        return self.exit_reason == "stop"


@dataclass(slots=True)
class FeatureRow:
    """Everything known at the close of one bar.

    Values are computed causally: a feature row at index ``i`` uses bars
    ``0..i`` only.  Daily context uses the last *completed* daily bar for
    intraday rows, which avoids the classic mistake of using today's daily
    close while trading the morning session.
    """

    index: int
    ts: datetime
    session: date
    open: float
    high: float
    low: float
    close: float
    volume: float

    prior_close: float | None = None
    gap_pct: float = 0.0
    minutes_since_open: int = 0
    session_progress: float = 0.0
    bar_in_session: int = 0

    ema9: float | None = None
    ema21: float | None = None
    ema50: float | None = None
    rsi14: float | None = None
    rsi_cross_up_30: bool = False
    rsi_cross_up_40: bool = False
    atr14: float | None = None
    atr_pct: float = 0.0
    realized_vol_pct: float = 0.0
    volume_ratio20: float = 1.0
    dollar_volume20: float = 0.0

    session_vwap: float | None = None
    price_vs_vwap_pct: float = 0.0
    price_vs_ema9_pct: float = 0.0
    close_above_vwap: bool = False
    close_above_ema9: bool = False

    rolling_high: float | None = None
    rolling_low: float | None = None
    drawdown_from_high_pct: float = 0.0
    close_drawdown_from_high_pct: float = 0.0
    drawdown_from_prior_close_pct: float = 0.0
    runup_from_low_pct: float = 0.0
    bars_since_low: int = 0

    last_swing_low: float | None = None
    prev_swing_low: float | None = None
    last_swing_high: float | None = None
    prev_swing_high: float | None = None
    higher_low: bool = False
    lower_high: bool = False
    close_above_prior_swing_high: bool = False

    episode_id: int | None = None
    episode_active: bool = False
    episode_start_index: int | None = None
    episode_reference_high: float | None = None
    episode_low: float | None = None
    episode_low_index: int | None = None
    episode_depth_pct: float = 0.0
    episode_recovery_pct: float = 0.0
    bars_since_episode_low: int = 0
    attempt_number: int = 1
    failed_bounces: int = 0
    failed_bounces_1pct: int = 0
    first_bounce_failed: bool = False
    bounce_speed_pct_per_bar: float = 0.0

    green_bar: bool = False
    close_above_prior_high: bool = False
    ema9_cross_up: bool = False
    vwap_cross_up: bool = False
    new_low_recent: bool = False

    daily_trend_score: float = 0.0
    daily_above_sma50: bool = False
    daily_above_sma200: bool = False
    daily_sma50_gt_sma200: bool = False
    daily_return_6m_pct: float = 0.0
    daily_distance_sma50_pct: float = 0.0
    daily_atr_pct: float = 0.0
    daily_range_5pct_days: int = 0
    daily_dip_count_60d: int = 0
    daily_avg_dollar_volume: float = 0.0
    daily_max_drawdown_1y_pct: float = 0.0
    daily_last_return_pct: float = 0.0
    daily_two_day_return_pct: float = 0.0
    daily_last_range_pct: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            key: value
            for key, value in self.__dict__.items()
            if key not in {"ts", "session"}
        }


@dataclass(frozen=True, slots=True)
class DailyContext:
    """Daily regime statistics known as of a given session."""

    as_of: date
    close: float
    sma20: float | None
    sma50: float | None
    sma200: float | None
    above_sma20: bool
    above_sma50: bool
    above_sma200: bool
    sma50_gt_sma200: bool
    return_6m_pct: float
    return_1y_pct: float
    distance_sma50_pct: float
    atr14_pct: float
    range_5pct_days_60d: int
    close_5pct_days_60d: int
    dip_count_60d: int
    avg_dollar_volume_60d: float
    max_drawdown_1y_pct: float
    trend_score: float
    last_return_pct: float = 0.0
    two_day_return_pct: float = 0.0
    last_range_pct: float = 0.0


@dataclass(frozen=True, slots=True)
class SignalSample:
    """A signal occurrence and the outcome of the trade it would have opened."""

    rule_id: str
    index: int
    ts: datetime
    features: FeatureRow
    outcome: TradeOutcome | None

    @property
    def success(self) -> bool:
        return bool(self.outcome and self.outcome.success)

    @property
    def fast_success(self) -> bool:
        return bool(self.outcome and self.outcome.fast_success)

    @property
    def net_return_pct(self) -> float:
        return self.outcome.net_return_pct if self.outcome else 0.0


@dataclass(slots=True)
class SimulatedTrade:
    """A non-overlapping trade produced by replaying a rule sequentially."""

    rule_id: str
    signal_index: int
    signal_ts: datetime
    outcome: TradeOutcome
    probability: float | None = None
    probability_fast: float | None = None
    features: FeatureRow | None = None


@dataclass(frozen=True, slots=True)
class EpisodeRecord:
    episode_id: int
    start_ts: datetime
    end_ts: datetime | None
    reference_high: float
    low: float
    low_ts: datetime
    depth_pct: float
    failed_bounces: int
    failed_bounces_1pct: int
    recovered: bool
    duration_bars: int
    max_bounce_pct: float
    # Every bounce leg in the episode, in %, measured from the low it started
    # at: each failed bounce (>= attempt_min_pct) plus the final leg.
    bounce_pcts: tuple[float, ...] = ()


@dataclass(slots=True)
class RuleStats:
    rule_id: str
    signals: int = 0
    signal_successes: int = 0
    signal_hit_rate: float = 0.0
    signal_hit_rate_low: float = 0.0
    signal_hit_rate_high: float = 0.0
    signal_net_ev_pct: float = 0.0
    trades: int = 0
    successes: int = 0
    hit_rate: float = 0.0
    hit_rate_low: float = 0.0
    hit_rate_high: float = 0.0
    net_ev_pct: float = 0.0
    gross_ev_pct: float = 0.0
    stop_rate: float = 0.0
    timeout_rate: float = 0.0
    fast_hit_rate: float = 0.0
    median_holding_minutes: float = 0.0
    mean_holding_minutes: float = 0.0
    trades_per_week: float = 0.0
    weekly_return_pct: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_mfe_pct: float = 0.0
    avg_mae_pct: float = 0.0
    profit_factor: float | None = None
    exposure_pct: float = 0.0
    periods: int = 0
    by_attempt: list[dict[str, object]] = field(default_factory=list)
    by_depth: list[dict[str, object]] = field(default_factory=list)
    by_time_of_day: list[dict[str, object]] = field(default_factory=list)
    by_runup: list[dict[str, object]] = field(default_factory=list)
    by_failed_bounce: list[dict[str, object]] = field(default_factory=list)
    trade_list: list[SimulatedTrade] = field(default_factory=list)


@dataclass(slots=True)
class ModelEvaluation:
    available: bool
    reason: str = ""
    model_type: str = "logistic_regression"
    samples: int = 0
    train_samples: int = 0
    test_samples: int = 0
    features: list[dict[str, object]] = field(default_factory=list)
    auc: float | None = None
    brier: float | None = None
    log_loss: float | None = None
    accuracy: float | None = None
    base_rate: float = 0.0
    calibration: list[dict[str, object]] = field(default_factory=list)
    walk_forward: list[dict[str, object]] = field(default_factory=list)
    threshold_curve: list[dict[str, object]] = field(default_factory=list)
    recommended_threshold: float = 0.5
    filtered_stats: dict[str, object] = field(default_factory=dict)
    spec: dict[str, object] | None = None
    fast: dict[str, object] | None = None
    oos_indices: list[int] = field(default_factory=list)
    oos_probabilities: list[float] = field(default_factory=list)
