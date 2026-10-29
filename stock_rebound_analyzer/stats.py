"""Statistics used to compare signal rules honestly."""

from __future__ import annotations

import math
from datetime import datetime
from statistics import mean, median
from typing import Callable, Iterable, Sequence

from .types import RuleStats, SignalSample, SimulatedTrade


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denom
    margin = (z / denom) * math.sqrt((p * (1.0 - p) / total) + (z2 / (4.0 * total * total)))
    return max(0.0, center - margin), min(1.0, center + margin)


def quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    q = max(0.0, min(1.0, q))
    position = q * (len(ordered) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def geometric_total(returns_pct: Iterable[float]) -> tuple[float, float, list[float]]:
    """Compound sequential trades.  Returns (total %, max DD %, equity path)."""

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    path: list[float] = [1.0]
    for value in returns_pct:
        equity *= 1.0 + value / 100.0
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, (equity / peak - 1.0) * 100.0)
        path.append(equity)
    return (equity - 1.0) * 100.0, max_dd, path


def profit_factor(returns_pct: Iterable[float]) -> float | None:
    gains = 0.0
    losses = 0.0
    for value in returns_pct:
        if value >= 0:
            gains += value
        else:
            losses += -value
    if losses == 0:
        return None
    return gains / losses


def auc_score(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    positives = [(s, y) for s, y in zip(scores, labels) if y]
    negatives = [(s, y) for s, y in zip(scores, labels) if not y]
    if not positives or not negatives:
        return None
    # Rank-based AUC with tie handling.
    combined = sorted(
        [(score, 1) for score, _ in positives] + [(score, 0) for score, _ in negatives],
        key=lambda item: item[0],
    )
    ranks: list[float] = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        average_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = average_rank
        i = j + 1
    positive_rank_sum = sum(
        ranks[i] for i in range(len(combined)) if combined[i][1] == 1
    )
    n_pos = len(positives)
    n_neg = len(negatives)
    return (positive_rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def brier_score(labels: Sequence[bool], probabilities: Sequence[float]) -> float | None:
    if not labels:
        return None
    return mean((p - (1.0 if y else 0.0)) ** 2 for p, y in zip(probabilities, labels))


def calibration_table(
    labels: Sequence[bool], probabilities: Sequence[float], bins: int = 5
) -> list[dict[str, object]]:
    if not labels:
        return []
    out: list[dict[str, object]] = []
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        members = [
            (p, y)
            for p, y in zip(probabilities, labels)
            if (low <= p < high) or (index == bins - 1 and p == high)
        ]
        if not members:
            continue
        out.append(
            {
                "bin": index,
                "low": round(low, 3),
                "high": round(high, 3),
                "count": len(members),
                "predicted": mean(p for p, _ in members),
                "actual": mean(1.0 if y else 0.0 for _, y in members),
            }
        )
    return out


def _bucket(
    samples: Sequence[SignalSample],
    predicate: Callable[[SignalSample], bool],
    label: str,
) -> dict[str, object] | None:
    members = [s for s in samples if s.outcome is not None and predicate(s)]
    if not members:
        return None
    successes = sum(1 for s in members if s.success)
    low, high = wilson_interval(successes, len(members))
    return {
        "bucket": label,
        "signals": len(members),
        "hit_rate": successes / len(members),
        "ci_low": low,
        "ci_high": high,
        "net_ev_pct": mean(s.net_return_pct for s in members),
    }


def _tables(
    samples: Sequence[SignalSample], timeframe: str
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    by_attempt = []
    for label, predicate in (
        ("1st attempt", lambda s: s.features.attempt_number == 1),
        ("2nd attempt", lambda s: s.features.attempt_number == 2),
        ("3rd+ attempt", lambda s: s.features.attempt_number >= 3),
    ):
        item = _bucket(samples, predicate, label)
        if item:
            by_attempt.append(item)

    by_failed = []
    for label, predicate in (
        ("no failed bounce", lambda s: s.features.failed_bounces_1pct == 0),
        ("1 failed bounce", lambda s: s.features.failed_bounces_1pct == 1),
        ("2+ failed bounces", lambda s: s.features.failed_bounces_1pct >= 2),
    ):
        item = _bucket(samples, predicate, label)
        if item:
            by_failed.append(item)

    by_depth = []
    for label, low, high in (
        ("5-7%", 5.0, 7.0),
        ("7-9%", 7.0, 9.0),
        ("9%+", 9.0, 1_000.0),
    ):
        item = _bucket(
            samples,
            lambda s, low=low, high=high: low <= s.features.episode_depth_pct < high,
            label,
        )
        if item:
            by_depth.append(item)

    by_time = []
    if timeframe != "1d":
        for label, low, high in (
            ("open 60m", 0, 60),
            ("60-180m", 60, 180),
            ("180-330m", 180, 330),
            ("last 60m", 330, 1_000),
        ):
            item = _bucket(
                samples,
                lambda s, low=low, high=high: low <= s.features.minutes_since_open < high,
                label,
            )
            if item:
                by_time.append(item)

    by_runup = []
    for label, low, high in (
        ("0-0.5%", 0.0, 0.5),
        ("0.5-1%", 0.5, 1.0),
        ("1-2%", 1.0, 2.0),
        ("2-3%", 2.0, 3.0),
    ):
        item = _bucket(
            samples,
            lambda s, low=low, high=high: low <= s.features.runup_from_low_pct < high,
            label,
        )
        if item:
            by_runup.append(item)

    return by_attempt, by_depth, by_time, by_runup, by_failed


def summarize_rule(
    rule_id: str,
    samples: Sequence[SignalSample],
    trades: Sequence[SimulatedTrade],
    *,
    period_start: datetime,
    period_end: datetime,
    timeframe: str,
) -> RuleStats:
    valid_samples = [s for s in samples if s.outcome is not None]
    period_days = max(
        1.0 / 24.0, (period_end - period_start).total_seconds() / 86_400.0
    )
    weeks = max(1.0, period_days / 7.0)

    stats = RuleStats(rule_id=rule_id, signals=len(valid_samples))
    if valid_samples:
        signal_successes = sum(1 for s in valid_samples if s.success)
        low, high = wilson_interval(signal_successes, len(valid_samples))
        stats.signal_successes = signal_successes
        stats.signal_hit_rate = signal_successes / len(valid_samples)
        stats.signal_hit_rate_low = low
        stats.signal_hit_rate_high = high
        stats.signal_net_ev_pct = mean(s.net_return_pct for s in valid_samples)

    stats.trades = len(trades)
    if trades:
        returns = [t.outcome.net_return_pct for t in trades]
        successes = sum(1 for t in trades if t.outcome.success)
        low, high = wilson_interval(successes, len(trades))
        total, max_dd, _ = geometric_total(returns)
        holding_minutes = [t.outcome.holding_trading_minutes for t in trades]
        stats.successes = successes
        stats.hit_rate = successes / len(trades)
        stats.hit_rate_low = low
        stats.hit_rate_high = high
        stats.net_ev_pct = mean(returns)
        stats.gross_ev_pct = mean(t.outcome.return_pct for t in trades)
        stats.stop_rate = mean(1.0 if t.outcome.is_stop else 0.0 for t in trades)
        stats.timeout_rate = mean(1.0 if t.outcome.is_timeout else 0.0 for t in trades)
        stats.fast_hit_rate = mean(1.0 if t.outcome.fast_success else 0.0 for t in trades)
        stats.median_holding_minutes = median(holding_minutes)
        stats.mean_holding_minutes = mean(holding_minutes)
        stats.trades_per_week = len(trades) / weeks
        stats.weekly_return_pct = (
            ((1.0 + total / 100.0) ** (1.0 / weeks) - 1.0) * 100.0
            if total > -100.0
            else -100.0
        )
        stats.total_return_pct = total
        stats.max_drawdown_pct = max_dd
        stats.avg_mfe_pct = mean(t.outcome.mfe_pct for t in trades)
        stats.avg_mae_pct = mean(t.outcome.mae_pct for t in trades)
        stats.profit_factor = profit_factor(returns)
        market_minutes = weeks * 5.0 * 390.0
        stats.exposure_pct = min(100.0, sum(holding_minutes) / market_minutes * 100.0)
        stats.periods = weeks

    (
        stats.by_attempt,
        stats.by_depth,
        stats.by_time_of_day,
        stats.by_runup,
        stats.by_failed_bounce,
    ) = _tables(valid_samples, timeframe)
    stats.trade_list = list(trades)
    return stats


def equity_curve(trades: Sequence[SimulatedTrade]) -> list[dict[str, object]]:
    equity = 1.0
    out: list[dict[str, object]] = []
    for trade in trades:
        equity *= 1.0 + trade.outcome.net_return_pct / 100.0
        out.append(
            {
                "ts": trade.outcome.exit_ts.isoformat(),
                "equity": equity,
                "return_pct": trade.outcome.net_return_pct,
                "rule_id": trade.rule_id,
            }
        )
    return out


def threshold_curve(
    samples: Sequence[SignalSample],
    probabilities: Sequence[float | None],
    *,
    period_start: datetime,
    period_end: datetime,
    min_trades: int,
) -> list[dict[str, object]]:
    pairs = [
        (s, p)
        for s, p in zip(samples, probabilities)
        if p is not None and s.outcome is not None
    ]
    if not pairs:
        return []
    period_days = max(
        1.0 / 24.0, (period_end - period_start).total_seconds() / 86_400.0
    )
    weeks = max(1.0, period_days / 7.0)
    # Build a non-overlapping sequence at each threshold.
    out: list[dict[str, object]] = []
    thresholds = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    for threshold in thresholds:
        selected = [s for s, p in pairs if p >= threshold]
        selected.sort(key=lambda s: s.index)
        trades: list[SignalSample] = []
        next_free = -1
        for sample in selected:
            if sample.outcome is None:
                continue
            if sample.outcome.entry_index < next_free:
                continue
            trades.append(sample)
            next_free = sample.outcome.exit_index + 1
        if len(trades) < min_trades:
            continue
        returns = [s.net_return_pct for s in trades]
        successes = sum(1 for s in trades if s.success)
        total, max_dd, _ = geometric_total(returns)
        out.append(
            {
                "threshold": threshold,
                "trades": len(trades),
                "hit_rate": successes / len(trades),
                "net_ev_pct": mean(returns),
                "trades_per_week": len(trades) / weeks,
                "weekly_return_pct": (
                    ((1.0 + total / 100.0) ** (1.0 / weeks) - 1.0) * 100.0
                    if total > -100.0
                    else -100.0
                ),
                "max_drawdown_pct": max_dd,
            }
        )
    return out
