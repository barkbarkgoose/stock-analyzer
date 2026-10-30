"""Blind replay: trade the strategy through history without seeing the future.

The hindsight view picks the best rule after looking at the whole window, which
flatters it.  The blind replay instead walks forward one session at a time.
Before each session opens it decides, using only what had already happened:

* which buy rule to use (the best track record among trades that had already
  closed, and only if that record is net positive), and
* where to stop watching a dip (the bounce cutoff, from dips that had already
  finished).

It then trades that session with those choices, one position at a time.  The
features and trade outcomes it relies on are causal (built only from past
bars), so they can be computed once and reused for every decision.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Sequence

from .bounces import resolve_cutoff
from .config import AnalysisConfig
from .rules import SignalRule, base_candidate, bounce_room_left, in_dip, trend_ok
from .types import EpisodeRecord, FeatureRow, SimulatedTrade, TradeOutcome

LADDER_TARGETS = (1.0, 1.5, 2.0, 2.5)
# Daily bars have ~250 sessions a year; re-deciding weekly is plenty there.
DAILY_DECISION_STEP = 5


@dataclass(slots=True)
class Prepared:
    """Rule firings and filters, computed once per profile."""

    rows: list[FeatureRow]
    rules: list[SignalRule]
    base: list[bool]
    recovery: list[float]
    fires: dict[str, list[bool]]
    sessions: list[date]
    session_first_index: dict[date, int]


@dataclass(slots=True)
class _Track:
    """One rule's sequential trades at one cutoff, with running totals."""

    trades: list[SimulatedTrade]
    exit_ts: list[datetime]
    equity: list[float]  # equity[k] = growth of 1.0 after the first k trades
    max_dd: list[float]  # worst drawdown (%, <= 0) over the first k trades


@dataclass(slots=True)
class BlindResult:
    trades: list[SimulatedTrade] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    start: datetime | None = None
    end: datetime | None = None
    row_cutoff: list[float | None] = field(default_factory=list)
    reason: str = ""


def prepare(
    rows: Sequence[FeatureRow], rules: Sequence[SignalRule], config: AnalysisConfig
) -> Prepared:
    tradable = [rule for rule in rules if rule.family != "baseline"]
    sessions: list[date] = []
    first: dict[date, int] = {}
    for i, row in enumerate(rows):
        if row.session not in first:
            first[row.session] = i
            sessions.append(row.session)
    return Prepared(
        rows=list(rows),
        rules=tradable,
        base=[base_candidate(row, config) for row in rows],
        recovery=[row.episode_recovery_pct for row in rows],
        fires={rule.id: [rule.evaluate(row) for row in rows] for rule in tradable},
        sessions=sessions,
        session_first_index=first,
    )


def _simulate(
    prep: Prepared,
    rule_id: str,
    cutoff: float,
    outcomes: Sequence[TradeOutcome | None],
) -> list[SimulatedTrade]:
    fires = prep.fires[rule_id]
    trades: list[SimulatedTrade] = []
    next_free = 0
    for i in range(min(len(prep.rows), len(outcomes))):
        if i < next_free or not fires[i] or not prep.base[i]:
            continue
        if prep.recovery[i] > cutoff + 1e-9:
            continue
        outcome = outcomes[i]
        if outcome is None:
            continue
        trades.append(
            SimulatedTrade(
                rule_id=rule_id,
                signal_index=i,
                signal_ts=prep.rows[i].ts,
                outcome=outcome,
                features=prep.rows[i],
            )
        )
        next_free = outcome.exit_index + 1
    return trades


def _track(trades: list[SimulatedTrade]) -> _Track:
    equity = [1.0]
    max_dd = [0.0]
    peak = 1.0
    for trade in trades:
        value = equity[-1] * (1.0 + trade.outcome.net_return_pct / 100.0)
        peak = max(peak, value)
        equity.append(value)
        max_dd.append(min(max_dd[-1], (value / peak - 1.0) * 100.0 if peak > 0 else 0.0))
    return _Track(
        trades=trades,
        exit_ts=[t.outcome.exit_ts for t in trades],
        equity=equity,
        max_dd=max_dd,
    )


def track_score(
    count: int, equity: float, max_dd: float, start: datetime, end: datetime
) -> float:
    """Same shape as the hindsight rank score: shrunk weekly return minus a
    drawdown penalty."""

    weeks = max(1.0, (end - start).total_seconds() / 86_400.0 / 7.0)
    weekly = -100.0 if equity <= 0 else (equity ** (1.0 / weeks) - 1.0) * 100.0
    shrink = count / (count + 10.0)
    return weekly * shrink - 0.20 * abs(max_dd)


def _decision_sessions(prep: Prepared, config: AnalysisConfig) -> list[date]:
    sessions = prep.sessions[config.blind_warmup_sessions :]
    if config.is_intraday:
        return sessions
    return sessions[::DAILY_DECISION_STEP]


def run_blind(
    prep: Prepared,
    outcomes: Sequence[TradeOutcome | None],
    episodes: Sequence[EpisodeRecord],
    config: AnalysisConfig,
) -> BlindResult:
    rows = prep.rows
    result = BlindResult(row_cutoff=[None] * len(rows))
    if not rows:
        result.reason = "No bars."
        return result
    decision_days = _decision_sessions(prep, config)
    if not decision_days:
        result.reason = (
            f"Fewer than {config.blind_warmup_sessions + 1} sessions of data; the blind "
            "trader needs a warm-up period before it can decide anything."
        )
        return result

    data_start = rows[0].ts
    tracks: dict[tuple[str, float], _Track] = {}

    def track_for(rule_id: str, cutoff: float) -> _Track:
        key = (rule_id, cutoff)
        if key not in tracks:
            tracks[key] = _track(_simulate(prep, rule_id, cutoff, outcomes))
        return tracks[key]

    # One decision per decision day; it stays in force until the next one.
    plan: dict[date, dict[str, Any]] = {}
    for day in decision_days:
        start_ts = rows[prep.session_first_index[day]].ts
        cutoff, source = resolve_cutoff(episodes, config, before=start_ts)
        best: tuple[float, str, int, float] | None = None
        for rule in prep.rules:
            track = track_for(rule.id, cutoff)
            known = bisect_left(track.exit_ts, start_ts)
            if known < config.min_trades_for_rule or track.equity[known] <= 1.0:
                continue
            score = track_score(
                known, track.equity[known], track.max_dd[known], data_start, start_ts
            )
            if best is None or score > best[0]:
                best = (score, rule.id, known, (track.equity[known] - 1.0) * 100.0)
        if best is None:
            reason = (
                "Sitting out: no buy rule had at least "
                f"{config.min_trades_for_rule} closed trades with a net-positive record yet."
            )
            decision = {
                "session": day,
                "rule_id": None,
                "cutoff_pct": cutoff,
                "cutoff_source": source,
                "train_trades": 0,
                "train_return_pct": None,
                "reason": reason,
            }
        else:
            decision = {
                "session": day,
                "rule_id": best[1],
                "cutoff_pct": cutoff,
                "cutoff_source": source,
                "train_trades": best[2],
                "train_return_pct": best[3],
                "reason": (
                    f"Best record so far: {best[2]} closed trades, "
                    f"{best[3]:+.2f}% total."
                ),
            }
        result.decisions.append(decision)
        plan[day] = decision

    result.start = rows[prep.session_first_index[decision_days[0]]].ts
    result.end = rows[-1].ts

    active: dict[str, Any] | None = None
    next_free = 0
    for i, row in enumerate(rows):
        active = plan.get(row.session, active)
        if active is None:
            continue
        cutoff = active["cutoff_pct"]
        result.row_cutoff[i] = cutoff
        rule_id = active["rule_id"]
        if rule_id is None or i < next_free or i >= len(outcomes):
            continue
        if not (prep.fires[rule_id][i] and prep.base[i]):
            continue
        if prep.recovery[i] > cutoff + 1e-9:
            continue
        outcome = outcomes[i]
        if outcome is None:
            continue
        result.trades.append(
            SimulatedTrade(
                rule_id=rule_id,
                signal_index=i,
                signal_ts=row.ts,
                outcome=outcome,
                features=row,
            )
        )
        next_free = outcome.exit_index + 1
    return result


def breakeven_hit_rate(config: AnalysisConfig) -> float:
    """Win rate at which +target and -stop trades net to zero after costs."""

    cost = (
        config.entry_slippage_bps + config.exit_slippage_bps + 2.0 * config.commission_bps
    ) / 100.0
    win = config.target_pct - cost
    loss = config.stop_pct + cost
    return loss / (win + loss) if win + loss > 0 else 1.0


def watch_bands(
    rows: Sequence[FeatureRow],
    config: AnalysisConfig,
    cutoffs: Sequence[float | None],
) -> list[dict[str, Any]]:
    """Contiguous stretches where the stock was in a dip.

    ``watch``: in a dip with bounce room left (buys allowed).
    ``extended``: still in the dip, but already bounced past the cutoff.
    """

    bands: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for i, row in enumerate(rows):
        cutoff = cutoffs[i] if i < len(cutoffs) else None
        kind: str | None = None
        if cutoff is not None and in_dip(row, config) and trend_ok(row, config):
            kind = "watch" if bounce_room_left(row, cutoff) else "extended"
        if current is not None and kind == current["kind"]:
            current["end"] = row.ts
            continue
        if current is not None:
            bands.append(current)
            current = None
        if kind is not None:
            current = {"kind": kind, "start": row.ts, "end": row.ts}
    if current is not None:
        bands.append(current)
    return bands
