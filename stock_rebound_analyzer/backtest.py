"""Sequential trade simulation for a confirmation rule."""

from __future__ import annotations

from .config import AnalysisConfig
from .rules import SignalRule, evaluates
from .types import FeatureRow, SimulatedTrade, SignalSample, TradeOutcome


def collect_samples(
    rule: SignalRule,
    rows: list[FeatureRow],
    outcomes: list[TradeOutcome | None],
    config: AnalysisConfig,
) -> list[SignalSample]:
    samples: list[SignalSample] = []
    for i, row in enumerate(rows):
        if i >= len(outcomes):
            break
        if not evaluates(row, rule, config):
            continue
        samples.append(
            SignalSample(
                rule_id=rule.id,
                index=i,
                ts=row.ts,
                features=row,
                outcome=outcomes[i],
            )
        )
    return samples


def simulate_rule_trades(
    rule: SignalRule,
    rows: list[FeatureRow],
    outcomes: list[TradeOutcome | None],
    config: AnalysisConfig,
) -> list[SimulatedTrade]:
    """Replay a rule with at most one open position at a time."""

    trades: list[SimulatedTrade] = []
    next_free_entry = 0
    for i, row in enumerate(rows):
        if i >= len(outcomes):
            break
        if i < next_free_entry:
            continue
        if not evaluates(row, rule, config):
            continue
        outcome = outcomes[i]
        if outcome is None:
            continue
        trades.append(
            SimulatedTrade(
                rule_id=rule.id,
                signal_index=i,
                signal_ts=row.ts,
                outcome=outcome,
                features=row,
            )
        )
        next_free_entry = outcome.exit_index + 1
    return trades


def simulate_with_probabilities(
    samples: list[SignalSample],
    probabilities: list[float | None],
    *,
    threshold: float,
    rule_id: str,
) -> list[SimulatedTrade]:
    """Sequential simulation using a model probability filter."""

    trades: list[SimulatedTrade] = []
    next_free_entry = 0
    for sample, probability in zip(samples, probabilities):
        if sample.outcome is None or probability is None:
            continue
        if probability < threshold:
            continue
        if sample.outcome.entry_index < next_free_entry:
            continue
        trades.append(
            SimulatedTrade(
                rule_id=rule_id,
                signal_index=sample.index,
                signal_ts=sample.ts,
                outcome=sample.outcome,
                probability=probability,
                features=sample.features,
            )
        )
        next_free_entry = sample.outcome.exit_index + 1
    return trades
