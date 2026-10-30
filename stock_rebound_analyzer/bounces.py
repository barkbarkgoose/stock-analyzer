"""How far this stock's dips actually bounce, and the per-stock watch cutoff.

The question this answers is not "does the dip fully recover?" but "once the
price turns up off a dip low, how far does it usually get before rolling over
or setting a new low?"  That is the room a +target% trade has to work with.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any, Sequence

from .config import AnalysisConfig
from .stats import quantile
from .types import EpisodeRecord

REACH_LEVELS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0)
MIN_EPISODES_FOR_AUTO = 4
# Conservative: plan around the bounce that 3 in 4 past dips reached, not the
# typical one.  A dip that fully recovers has a huge "biggest bounce", which
# would otherwise drag the cutoff up to "almost recovered".
CUTOFF_QUANTILE = 0.25
MIN_CUTOFF_PCT = 0.5
MAX_CUTOFF_PCT = 8.0


def completed_episodes(
    episodes: Sequence[EpisodeRecord], before: datetime | None = None
) -> list[EpisodeRecord]:
    """Episodes that had finished (strictly) before ``before``."""

    return [
        e
        for e in episodes
        if e.end_ts is not None and (before is None or e.end_ts < before)
    ]


def resolve_cutoff(
    episodes: Sequence[EpisodeRecord],
    config: AnalysisConfig,
    *,
    before: datetime | None = None,
) -> tuple[float, str]:
    """The run-up cutoff and where it came from ("auto" or "fixed")."""

    if config.runup_cutoff_mode != "auto":
        return config.max_runup_from_low_pct, "fixed"
    done = completed_episodes(episodes, before)
    if len(done) < MIN_EPISODES_FOR_AUTO:
        return config.max_runup_from_low_pct, "fallback"
    reliable = quantile([e.max_bounce_pct for e in done], CUTOFF_QUANTILE)
    cutoff = min(MAX_CUTOFF_PCT, max(MIN_CUTOFF_PCT, reliable - config.target_pct))
    return round(cutoff, 2), "auto"


def bounce_profile(
    episodes: Sequence[EpisodeRecord], config: AnalysisConfig
) -> dict[str, Any]:
    done = completed_episodes(episodes)
    cutoff, source = resolve_cutoff(episodes, config)
    biggest = [e.max_bounce_pct for e in done]
    legs = [leg for e in done for leg in e.bounce_pcts]
    target = config.target_pct

    reach = [
        {
            "level_pct": level,
            "episodes": sum(1 for b in biggest if b >= level),
            "episodes_pct": (
                sum(1 for b in biggest if b >= level) / len(biggest) if biggest else 0.0
            ),
            "legs": sum(1 for b in legs if b >= level),
            "legs_pct": sum(1 for b in legs if b >= level) / len(legs) if legs else 0.0,
        }
        for level in sorted({*REACH_LEVELS, target})
    ]

    if not done:
        interpretation = "No completed dips yet, so there is no bounce history to learn from."
    else:
        reached = sum(1 for b in biggest if b >= target)
        typical = median(biggest)
        interpretation = (
            f"In {len(done)} past dips the price climbed at least {target:g}% off the low "
            f"in {reached} of them. The best bounce in a typical dip reached about "
            f"{typical:.1f}%."
        )
        if legs:
            leg_hits = sum(1 for b in legs if b >= target)
            interpretation += (
                f" Counting every bounce attempt (fake ones included), {leg_hits} of "
                f"{len(legs)} reached {target:g}%."
            )

    if source == "auto":
        reliable = quantile(biggest, CUTOFF_QUANTILE)
        cutoff_text = (
            f"Stop watching once the price is {cutoff:.2f}% off the low. 3 in 4 past dips "
            f"here bounced at least {reliable:.2f}% off the low, so past {cutoff:.2f}% "
            f"there is often less than {target:g}% of room left."
        )
        if reliable - target < MIN_CUTOFF_PCT:
            cutoff_text += (
                f" That leaves very little room for a {target:g}% target on this stock."
            )
    elif source == "fallback":
        cutoff_text = (
            f"Fewer than {MIN_EPISODES_FOR_AUTO} completed dips, so the fixed fallback "
            f"cutoff of {cutoff:.2f}% is used until there is more history."
        )
    else:
        cutoff_text = f"Fixed cutoff: stop watching once the price is {cutoff:.2f}% off the low."

    return {
        "episodes": len(done),
        "legs": len(legs),
        "median_biggest_bounce_pct": median(biggest) if biggest else None,
        "p25_biggest_bounce_pct": quantile(biggest, 0.25) if biggest else None,
        "p75_biggest_bounce_pct": quantile(biggest, 0.75) if biggest else None,
        "median_leg_pct": median(legs) if legs else None,
        "reach": reach,
        "cutoff_pct": cutoff,
        "cutoff_source": source,
        "cutoff_text": cutoff_text,
        "interpretation": interpretation,
    }
