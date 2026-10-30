"""Buy-signal confirmation rules.

The dip itself is *not* a buy signal.  Every rule below is evaluated only while
a multi-leg dip episode is active, and most require evidence that the rebound
has actually started: a higher low, a reclaim of a short EMA/VWAP, a close
above the prior bar or a prior swing high, volume expansion, or an RSI reclaim.

Each rule is a list of named checks and fires only when all of them pass.  The
names are what the UI shows as the live "buy checklist", so the checklist is
always exactly the trigger rather than a separate approximation of it.

The profile compares rules on identical entries/outcomes (same triple-barrier
labels), so differences come from the signal timing rather than from labelling
choices.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import AnalysisConfig
from .types import SESSION_MINUTES, FeatureRow

Check = tuple[str, Callable[[FeatureRow], bool]]


@dataclass(frozen=True, slots=True)
class SignalRule:
    id: str
    name: str
    description: str
    family: str
    # One plain-English sentence finishing "Buy when ...".
    plain: str
    checks: tuple[Check, ...] = ()
    supports_daily: bool = True

    def evaluate(self, row: FeatureRow, cfg: AnalysisConfig | None = None) -> bool:
        return all(test(row) for _, test in self.checks)

    def checklist(self, row: FeatureRow) -> list[dict[str, object]]:
        return [{"label": label, "ok": bool(test(row))} for label, test in self.checks]

    @property
    def confirmations(self) -> tuple[str, ...]:
        return tuple(label for label, _ in self.checks)


# ---------------------------------------------------------------------------
# Shared checks
# ---------------------------------------------------------------------------

GREEN_ABOVE_PRIOR_HIGH: Check = (
    "Rising bar closes above the previous bar's high",
    lambda r: bool(r.green_bar and r.close_above_prior_high),
)
GREEN_BAR: Check = ("Rising (green) bar", lambda r: bool(r.green_bar))
ABOVE_PRIOR_HIGH: Check = (
    "Closes above the previous bar's high",
    lambda r: bool(r.close_above_prior_high),
)
HIGHER_LOW: Check = ("Higher low has formed", lambda r: bool(r.higher_low))
NO_FRESH_LOW: Check = (
    "No new low in the last 3 bars",
    lambda r: not r.new_low_recent,
)
STRUCTURE_TURNED: Check = (
    "Structure turned (higher low or close above the last peak)",
    lambda r: bool(r.higher_low or r.close_above_prior_swing_high),
)


def _off_low(pct: float) -> Check:
    return (f"At least {pct:g}% off the low", lambda r: r.runup_from_low_pct >= pct)


def _volume(ratio: float, label: str) -> Check:
    return (label, lambda r: r.volume_ratio20 >= ratio)


def _balanced_votes(row: FeatureRow) -> int:
    votes = 0
    if row.ema9 is not None:
        votes += int(row.ema9_cross_up or (row.green_bar and row.close_above_ema9))
    if row.session_vwap is not None:
        votes += int(row.vwap_cross_up or row.close_above_vwap)
    votes += int(row.green_bar and row.close_above_prior_high)
    votes += int(row.higher_low)
    return votes


RULES: tuple[SignalRule, ...] = (
    SignalRule(
        id="dip_close",
        name="Buy every dip bar (baseline)",
        description=(
            "Enters on any bar while a >= threshold dip episode is active. "
            "This is the naive baseline the confirmations must beat."
        ),
        family="baseline",
        plain="any bar during the dip — no confirmation at all (yardstick only)",
        checks=(),
    ),
    SignalRule(
        id="green_reclaim",
        name="Green bar reclaim",
        description=(
            "Green bar, closes above the prior bar's high, with at least 1.05x "
            "recent volume."
        ),
        family="single",
        plain="a rising bar closes above the previous bar's high on slightly above-normal volume",
        checks=(
            GREEN_ABOVE_PRIOR_HIGH,
            _volume(1.05, "Volume at least 1.05× normal"),
        ),
    ),
    SignalRule(
        id="ema_reclaim",
        name="9-EMA reclaim",
        description="Close crosses back above the 9-EMA on a green bar.",
        family="single",
        plain="the price closes back above its short-term (9-bar) average on a rising bar",
        checks=(
            GREEN_BAR,
            ("Crosses back above the 9-EMA", lambda r: bool(r.ema9_cross_up)),
        ),
    ),
    SignalRule(
        id="vwap_reclaim",
        name="VWAP reclaim",
        description="Close crosses back above session VWAP on a green bar.",
        family="single",
        plain="the price closes back above today's average traded price (VWAP) on a rising bar",
        supports_daily=False,
        checks=(
            GREEN_BAR,
            ("Crosses back above session VWAP", lambda r: bool(r.vwap_cross_up)),
        ),
    ),
    SignalRule(
        id="higher_low_break",
        name="Higher low + swing break",
        description=(
            "A confirmed higher low plus a close above the last confirmed swing "
            "high. This is the classic 'structure has turned' confirmation."
        ),
        family="structure",
        plain="the dip makes a higher low and then closes above its last bounce peak",
        checks=(
            HIGHER_LOW,
            (
                "Closes above the last bounce peak",
                lambda r: bool(r.close_above_prior_swing_high),
            ),
            _off_low(0.3),
        ),
    ),
    SignalRule(
        id="bounce_hold",
        name="Bounce hold",
        description=(
            "At least 0.6% off the dip low, closing above the prior bar high, "
            "with no new low in the last three bars."
        ),
        family="structure",
        plain="the bounce is at least 0.6% off the low, closes above the previous bar's high, and hasn't made a new low for 3 bars",
        checks=(_off_low(0.6), ABOVE_PRIOR_HIGH, NO_FRESH_LOW),
    ),
    SignalRule(
        id="rsi_reclaim",
        name="RSI reclaim",
        description="RSI(14) crosses up through 30 or 40 on a green reclaim bar.",
        family="momentum",
        plain="momentum (RSI) turns back up out of oversold on a rising bar above the previous high",
        checks=(
            (
                "RSI crosses up through 30 or 40",
                lambda r: bool(r.rsi_cross_up_30 or r.rsi_cross_up_40),
            ),
            GREEN_ABOVE_PRIOR_HIGH,
        ),
    ),
    SignalRule(
        id="volume_reversal",
        name="Volume reversal",
        description=(
            "1.5x volume expansion, green bar, prior high reclaimed, and at "
            "least 0.3% off the low."
        ),
        family="momentum",
        plain="a rising bar on 1.5× normal volume closes above the previous high, at least 0.3% off the low",
        checks=(
            _volume(1.5, "Volume at least 1.5× normal"),
            GREEN_ABOVE_PRIOR_HIGH,
            _off_low(0.3),
        ),
    ),
    SignalRule(
        id="composite_balanced",
        name="Balanced composite",
        description=(
            "At least two of: green/prior-high reclaim, EMA reclaim, VWAP "
            "reclaim, higher low. Requires a structural break and no fresh low."
        ),
        family="composite",
        plain="at least two turn signals agree, the structure has turned, and no new low has printed for 3 bars",
        checks=(
            (
                "2+ of: rising bar above prior high, above 9-EMA, above VWAP, higher low",
                lambda r: _balanced_votes(r) >= 2,
            ),
            STRUCTURE_TURNED,
            _off_low(0.3),
            NO_FRESH_LOW,
            _volume(1.0, "Volume at least normal"),
        ),
    ),
    SignalRule(
        id="composite_conservative",
        name="Conservative composite",
        description=(
            "Green reclaim + higher low + EMA or VWAP reclaim + volume, at "
            "least 0.3% off the low. Fewer trades, higher precision."
        ),
        family="composite",
        plain="a rising bar closes above the previous high, the low is higher than the last one, price is back above its short-term average or VWAP, and volume is normal or better",
        checks=(
            GREEN_ABOVE_PRIOR_HIGH,
            HIGHER_LOW,
            (
                "Above the 9-EMA or session VWAP",
                lambda r: bool(
                    r.close_above_ema9
                    or (r.session_vwap is not None and r.close_above_vwap)
                ),
            ),
            _volume(1.0, "Volume at least normal"),
            _off_low(0.3),
        ),
    ),
    SignalRule(
        id="second_attempt",
        name="Second attempt (structure)",
        description=(
            "Requires a failed first bounce, then a higher low and a reclaim. "
            "This is the explicit anti-fake-rebound rule."
        ),
        family="second_attempt",
        plain="one bounce has already failed, then the price makes a higher low and closes above a recent high",
        checks=(
            ("A previous bounce already failed", lambda r: r.failed_bounces >= 1),
            HIGHER_LOW,
            GREEN_BAR,
            (
                "Closes above the last peak or the previous bar's high",
                lambda r: bool(
                    r.close_above_prior_swing_high or r.close_above_prior_high
                ),
            ),
            _off_low(0.3),
        ),
    ),
    SignalRule(
        id="second_attempt_soft",
        name="Second attempt (soft)",
        description=(
            "Requires a failed >=1% bounce, then a green bar above the prior "
            "high and 0.4% off the low."
        ),
        family="second_attempt",
        plain="a 1%+ bounce has already failed, then a rising bar closes above the previous high without a fresh low",
        checks=(
            (
                "A previous 1%+ bounce already failed",
                lambda r: r.failed_bounces_1pct >= 1,
            ),
            GREEN_ABOVE_PRIOR_HIGH,
            _off_low(0.4),
            NO_FRESH_LOW,
        ),
    ),
    SignalRule(
        id="deep_dip_reclaim",
        name="Deep dip reclaim",
        description=(
            "Only for episodes at least 7% deep: green reclaim plus a "
            "structural break."
        ),
        family="deep_dip",
        plain="the dip is at least 7% deep and a rising bar closes above the previous high with the structure turning",
        checks=(
            ("Dip is at least 7% deep", lambda r: r.episode_depth_pct >= 7.0),
            GREEN_ABOVE_PRIOR_HIGH,
            STRUCTURE_TURNED,
            _off_low(0.3),
        ),
    ),
)

RULE_BY_ID = {rule.id: rule for rule in RULES}


def available_rules(config: AnalysisConfig) -> list[SignalRule]:
    rules = list(RULES)
    if not config.is_intraday:
        rules = [rule for rule in rules if rule.supports_daily]
    if config.enabled_rules:
        wanted = set(config.enabled_rules)
        rules = [rule for rule in rules if rule.id in wanted]
    return rules


# ---------------------------------------------------------------------------
# Watch window (filters shared by every rule)
# ---------------------------------------------------------------------------


def in_dip(row: FeatureRow, config: AnalysisConfig) -> bool:
    return bool(
        row.episode_active
        and row.episode_depth_pct + 1e-9 >= config.dip_threshold_pct
    )


def bounce_room_left(row: FeatureRow, cutoff_pct: float) -> bool:
    # Measured from the episode's own low, not a rolling window, so a dip that
    # drifts sideways for days does not quietly re-arm the watch.
    return row.episode_recovery_pct <= cutoff_pct + 1e-9


def in_trading_window(row: FeatureRow, config: AnalysisConfig) -> bool:
    if not config.is_intraday:
        return True
    minutes = row.minutes_since_open
    return (
        minutes >= config.exclude_first_minutes
        and minutes <= SESSION_MINUTES - config.exclude_last_minutes
    )


def trend_ok(row: FeatureRow, config: AnalysisConfig) -> bool:
    return not (
        config.only_uptrend_signals
        and row.daily_trend_score < config.uptrend_min_score
    )


def base_candidate(row: FeatureRow, config: AnalysisConfig) -> bool:
    """Every candidate filter except the bounce cutoff."""

    return (
        in_dip(row, config)
        and in_trading_window(row, config)
        and trend_ok(row, config)
    )


def is_candidate_bar(
    row: FeatureRow, config: AnalysisConfig, cutoff_pct: float | None = None
) -> bool:
    """Filters that apply to every rule's evaluation."""

    cutoff = config.max_runup_from_low_pct if cutoff_pct is None else cutoff_pct
    return base_candidate(row, config) and bounce_room_left(row, cutoff)


def watch_checklist(row: FeatureRow, config: AnalysisConfig) -> list[dict[str, object]]:
    items = [
        {
            "label": f"Down at least {config.dip_threshold_pct:g}% from the recent high",
            "ok": in_dip(row, config),
        },
        {
            "label": (
                f"Bounce room left (no more than {config.max_runup_from_low_pct:.2f}% "
                "off the dip low)"
            ),
            "ok": bool(row.episode_active)
            and bounce_room_left(row, config.max_runup_from_low_pct),
        },
    ]
    if config.is_intraday:
        items.append(
            {
                "label": (
                    f"Not the first {config.exclude_first_minutes} or last "
                    f"{config.exclude_last_minutes} minutes of the session"
                ),
                "ok": in_trading_window(row, config),
            }
        )
    if config.only_uptrend_signals:
        items.append(
            {
                "label": f"Daily uptrend score at least {config.uptrend_min_score:g}",
                "ok": trend_ok(row, config),
            }
        )
    return items


def evaluates(
    row: FeatureRow, rule: SignalRule, config: AnalysisConfig
) -> bool:
    return is_candidate_bar(row, config) and rule.evaluate(row, config)
