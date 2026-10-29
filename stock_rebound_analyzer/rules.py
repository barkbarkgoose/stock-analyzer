"""Buy-signal confirmation rules.

The dip itself is *not* a buy signal.  Every rule below is evaluated only while
a multi-leg dip episode is active, and most require evidence that the rebound
has actually started: a higher low, a reclaim of a short EMA/VWAP, a close
above the prior bar or a prior swing high, volume expansion, or an RSI reclaim.

Rule definitions are intentionally simple and readable.  The profile compares
them on identical entries/outcomes (same triple-barrier labels), so differences
come from the signal timing rather than from labelling choices.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import AnalysisConfig
from .types import SESSION_MINUTES, FeatureRow


@dataclass(frozen=True, slots=True)
class SignalRule:
    id: str
    name: str
    description: str
    family: str
    evaluate: Callable[[FeatureRow, AnalysisConfig], bool]
    supports_daily: bool = True
    confirmations: tuple[str, ...] = ()


def _green_reclaim(row: FeatureRow) -> bool:
    return (
        row.green_bar
        and row.close_above_prior_high
        and row.volume_ratio20 >= 1.05
    )


def _vwap_available(row: FeatureRow) -> bool:
    return row.session_vwap is not None


def _structural_break(row: FeatureRow) -> bool:
    return row.higher_low or row.close_above_prior_swing_high


def _dip_close(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return True


def _green_reclaim_rule(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return _green_reclaim(row)


def _ema_reclaim_rule(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(row.ema9_cross_up and row.green_bar)


def _vwap_reclaim_rule(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(row.vwap_cross_up and row.green_bar)


def _higher_low_break_rule(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(
        row.higher_low
        and row.close_above_prior_swing_high
        and row.runup_from_low_pct >= 0.3
    )


def _bounce_hold_rule(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(
        row.runup_from_low_pct >= 0.6
        and row.close_above_prior_high
        and not row.new_low_recent
    )


def _rsi_reclaim_rule(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(
        (row.rsi_cross_up_30 or row.rsi_cross_up_40)
        and row.green_bar
        and row.close_above_prior_high
    )


def _volume_reversal_rule(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(
        row.volume_ratio20 >= 1.5
        and row.green_bar
        and row.close_above_prior_high
        and row.runup_from_low_pct >= 0.3
    )


def _composite_balanced(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    components = 0
    if row.ema9 is not None:
        components += int(
            row.ema9_cross_up or (row.green_bar and row.close_above_ema9)
        )
    if _vwap_available(row):
        components += int(row.vwap_cross_up or row.close_above_vwap)
    components += int(row.green_bar and row.close_above_prior_high)
    components += int(row.higher_low)
    return bool(
        components >= 2
        and _structural_break(row)
        and row.runup_from_low_pct >= 0.3
        and not row.new_low_recent
        and row.volume_ratio20 >= 1.0
    )


def _composite_conservative(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(
        row.green_bar
        and row.close_above_prior_high
        and row.higher_low
        and (row.close_above_ema9 or (row.session_vwap is not None and row.close_above_vwap))
        and row.volume_ratio20 >= 1.0
        and row.runup_from_low_pct >= 0.3
    )


def _second_attempt(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(
        row.failed_bounces >= 1
        and row.higher_low
        and row.green_bar
        and (row.close_above_prior_swing_high or row.close_above_prior_high)
        and row.runup_from_low_pct >= 0.3
    )


def _second_attempt_soft(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(
        row.failed_bounces_1pct >= 1
        and row.green_bar
        and row.close_above_prior_high
        and row.runup_from_low_pct >= 0.4
        and not row.new_low_recent
    )


def _deep_dip_reclaim(row: FeatureRow, cfg: AnalysisConfig) -> bool:
    return bool(
        row.episode_depth_pct >= 7.0
        and row.green_bar
        and row.close_above_prior_high
        and _structural_break(row)
        and row.runup_from_low_pct >= 0.3
    )


RULES: tuple[SignalRule, ...] = (
    SignalRule(
        id="dip_close",
        name="Buy every dip bar (baseline)",
        description=(
            "Enters on any bar while a >= threshold dip episode is active. "
            "This is the naive baseline the confirmations must beat."
        ),
        family="baseline",
        evaluate=_dip_close,
        confirmations=(),
    ),
    SignalRule(
        id="green_reclaim",
        name="Green bar reclaim",
        description=(
            "Green bar, closes above the prior bar's high, with at least 1.05x "
            "recent volume."
        ),
        family="single",
        evaluate=_green_reclaim_rule,
        confirmations=("green bar", "prior high reclaimed", "volume > 1.05x"),
    ),
    SignalRule(
        id="ema_reclaim",
        name="9-EMA reclaim",
        description="Close crosses back above the 9-EMA on a green bar.",
        family="single",
        evaluate=_ema_reclaim_rule,
        confirmations=("green bar", "9-EMA reclaimed"),
    ),
    SignalRule(
        id="vwap_reclaim",
        name="VWAP reclaim",
        description="Close crosses back above session VWAP on a green bar.",
        family="single",
        evaluate=_vwap_reclaim_rule,
        supports_daily=False,
        confirmations=("green bar", "session VWAP reclaimed"),
    ),
    SignalRule(
        id="higher_low_break",
        name="Higher low + swing break",
        description=(
            "A confirmed higher low plus a close above the last confirmed swing "
            "high. This is the classic 'structure has turned' confirmation."
        ),
        family="structure",
        evaluate=_higher_low_break_rule,
        confirmations=("higher low", "prior swing high reclaimed", "0.3% off low"),
    ),
    SignalRule(
        id="bounce_hold",
        name="Bounce hold",
        description=(
            "At least 0.6% off the dip low, closing above the prior bar high, "
            "with no new low in the last three bars."
        ),
        family="structure",
        evaluate=_bounce_hold_rule,
        confirmations=("0.6% off low", "prior bar high reclaimed", "no fresh low"),
    ),
    SignalRule(
        id="rsi_reclaim",
        name="RSI reclaim",
        description="RSI(14) crosses up through 30 or 40 on a green reclaim bar.",
        family="momentum",
        evaluate=_rsi_reclaim_rule,
        confirmations=("RSI cross", "green bar", "prior high reclaimed"),
    ),
    SignalRule(
        id="volume_reversal",
        name="Volume reversal",
        description=(
            "1.5x volume expansion, green bar, prior high reclaimed, and at "
            "least 0.3% off the low."
        ),
        family="momentum",
        evaluate=_volume_reversal_rule,
        confirmations=("volume > 1.5x", "green bar", "0.3% off low"),
    ),
    SignalRule(
        id="composite_balanced",
        name="Balanced composite",
        description=(
            "At least two of: green/prior-high reclaim, EMA reclaim, VWAP "
            "reclaim, higher low. Requires a structural break and no fresh low."
        ),
        family="composite",
        evaluate=_composite_balanced,
        confirmations=(
            "2 confirmations",
            "structural break",
            "0.3% off low",
            "no fresh low",
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
        evaluate=_composite_conservative,
        confirmations=(
            "green reclaim",
            "higher low",
            "EMA/VWAP reclaim",
            "volume",
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
        evaluate=_second_attempt,
        confirmations=(
            "failed first bounce",
            "higher low",
            "green reclaim",
            "0.3% off low",
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
        evaluate=_second_attempt_soft,
        confirmations=(
            "failed 1% bounce",
            "green bar",
            "prior high reclaimed",
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
        evaluate=_deep_dip_reclaim,
        confirmations=("dip >= 7%", "green reclaim", "structural break"),
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


def is_candidate_bar(row: FeatureRow, config: AnalysisConfig) -> bool:
    """Filters that apply to every rule's evaluation."""

    if not row.episode_active:
        return False
    if row.episode_depth_pct + 1e-9 < config.dip_threshold_pct:
        return False
    if row.runup_from_low_pct > config.max_runup_from_low_pct + 1e-9:
        # The easy part of the rebound is already gone.  A 1% target from here
        # would require a near-full recovery of the dip.
        return False
    if config.is_intraday:
        minutes = row.minutes_since_open
        if minutes < config.exclude_first_minutes:
            return False
        if minutes > SESSION_MINUTES - config.exclude_last_minutes:
            return False
    if config.only_uptrend_signals and row.daily_trend_score < config.uptrend_min_score:
        return False
    return True


def evaluates(
    row: FeatureRow, rule: SignalRule, config: AnalysisConfig
) -> bool:
    return is_candidate_bar(row, config) and rule.evaluate(row, config)
