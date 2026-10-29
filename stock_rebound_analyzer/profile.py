"""Build the complete, reproducible profile for one symbol."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from statistics import mean, median
from typing import Any, Sequence

from .backtest import (
    collect_samples,
    simulate_rule_trades,
    simulate_with_probabilities,
)
from .bars import normalize_bars, resample_daily
from .config import AnalysisConfig
from .daily import build_daily_contexts, build_daily_profile
from .features import FeatureSeries, build_features
from .indicators import session_date
from .labels import label_all
from .model import predict_probability, train_model
from .rules import available_rules, is_candidate_bar
from .signal_read import build_signal_read
from .stats import equity_curve, geometric_total, summarize_rule, threshold_curve
from .types import (
    Bar,
    EpisodeRecord,
    FeatureRow,
    ModelEvaluation,
    RuleStats,
    SignalSample,
    SimulatedTrade,
)

ENGINE_VERSION = "3.5"
DISCLAIMER = (
    "Historical research only. Past behaviour does not guarantee future results; "
    "this tool does not place orders."
)


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value.isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 6)
    return value


def _stats_summary(stats: RuleStats, rank_score: float | None = None) -> dict[str, Any]:
    data = {
        "rule_id": stats.rule_id,
        "signals": stats.signals,
        "signal_successes": stats.signal_successes,
        "signal_hit_rate": stats.signal_hit_rate,
        "signal_hit_rate_low": stats.signal_hit_rate_low,
        "signal_hit_rate_high": stats.signal_hit_rate_high,
        "signal_net_ev_pct": stats.signal_net_ev_pct,
        "trades": stats.trades,
        "successes": stats.successes,
        "hit_rate": stats.hit_rate,
        "hit_rate_low": stats.hit_rate_low,
        "hit_rate_high": stats.hit_rate_high,
        "net_ev_pct": stats.net_ev_pct,
        "gross_ev_pct": stats.gross_ev_pct,
        "stop_rate": stats.stop_rate,
        "timeout_rate": stats.timeout_rate,
        "fast_hit_rate": stats.fast_hit_rate,
        "median_holding_minutes": stats.median_holding_minutes,
        "mean_holding_minutes": stats.mean_holding_minutes,
        "trades_per_week": stats.trades_per_week,
        "weekly_return_pct": stats.weekly_return_pct,
        "total_return_pct": stats.total_return_pct,
        "max_drawdown_pct": stats.max_drawdown_pct,
        "avg_mfe_pct": stats.avg_mfe_pct,
        "avg_mae_pct": stats.avg_mae_pct,
        "profit_factor": stats.profit_factor,
        "exposure_pct": stats.exposure_pct,
        "periods": stats.periods,
        "by_attempt": stats.by_attempt,
        "by_depth": stats.by_depth,
        "by_time_of_day": stats.by_time_of_day,
        "by_runup": stats.by_runup,
        "by_failed_bounce": stats.by_failed_bounce,
    }
    if rank_score is not None:
        data["rank_score"] = rank_score
    return data


def _rank_score(stats: RuleStats) -> float:
    # Shrink the weekly return for small samples, then penalise drawdown.  The
    # goal is consistency, not the single best in-sample week.
    shrink = stats.trades / (stats.trades + 10.0) if stats.trades else 0.0
    return stats.weekly_return_pct * shrink - 0.20 * abs(stats.max_drawdown_pct)


def _weekly_return(trades: Sequence[SimulatedTrade], start: datetime, end: datetime) -> float:
    weeks = max(1.0, (end - start).total_seconds() / 86_400.0 / 7.0)
    total, _, _ = geometric_total(t.outcome.net_return_pct for t in trades)
    if total <= -100.0:
        return -100.0
    return ((1.0 + total / 100.0) ** (1.0 / weeks) - 1.0) * 100.0


def _samples_from_trades(trades: Sequence[SimulatedTrade]) -> list[SignalSample]:
    return [
        SignalSample(
            rule_id=trade.rule_id,
            index=trade.signal_index,
            ts=trade.signal_ts,
            features=trade.features or _empty_row(trade.signal_ts),
            outcome=trade.outcome,
        )
        for trade in trades
    ]


def _empty_row(ts: datetime) -> FeatureRow:
    return FeatureRow(
        index=0,
        ts=ts,
        session=ts.date(),
        open=0.0,
        high=0.0,
        low=0.0,
        close=0.0,
        volume=0.0,
    )


def _trade_to_dict(trade: SimulatedTrade) -> dict[str, Any]:
    outcome = trade.outcome
    row = trade.features
    features: dict[str, Any] = {}
    if row is not None:
        features = {
            "episode_depth_pct": row.episode_depth_pct,
            "drawdown_from_high_pct": row.drawdown_from_high_pct,
            "drawdown_from_prior_close_pct": row.drawdown_from_prior_close_pct,
            "runup_from_low_pct": row.runup_from_low_pct,
            "bars_since_episode_low": row.bars_since_episode_low,
            "attempt_number": row.attempt_number,
            "failed_bounces": row.failed_bounces,
            "failed_bounces_1pct": row.failed_bounces_1pct,
            "volume_ratio20": row.volume_ratio20,
            "rsi14": row.rsi14,
            "atr_pct": row.atr_pct,
            "price_vs_vwap_pct": row.price_vs_vwap_pct,
            "higher_low": row.higher_low,
            "close_above_prior_swing_high": row.close_above_prior_swing_high,
            "minutes_since_open": row.minutes_since_open,
            "daily_trend_score": row.daily_trend_score,
            "gap_pct": row.gap_pct,
        }
    return {
        "rule_id": trade.rule_id,
        "signal_index": trade.signal_index,
        "signal_ts": _iso(trade.signal_ts),
        "entry_ts": _iso(outcome.entry_ts),
        "exit_ts": _iso(outcome.exit_ts),
        "entry_price": outcome.entry_price,
        "exit_price": outcome.exit_price,
        "return_pct": outcome.return_pct,
        "net_return_pct": outcome.net_return_pct,
        "exit_reason": outcome.exit_reason,
        "success": outcome.success,
        "fast_success": outcome.fast_success,
        "holding_bars": outcome.holding_bars,
        "holding_minutes": outcome.holding_minutes,
        "holding_trading_minutes": outcome.holding_trading_minutes,
        "mfe_pct": outcome.mfe_pct,
        "mae_pct": outcome.mae_pct,
        "target_price": outcome.target_price,
        "stop_price": outcome.stop_price,
        "probability": trade.probability,
        "probability_fast": trade.probability_fast,
        "features": features,
    }


def _episodes_to_dict(episodes: Sequence[EpisodeRecord], limit: int = 60) -> list[dict[str, Any]]:
    selected = list(episodes)[-limit:]
    return [
        {
            "id": episode.episode_id,
            "start": _iso(episode.start_ts),
            "end": _iso(episode.end_ts),
            "reference_high": episode.reference_high,
            "low": episode.low,
            "low_ts": _iso(episode.low_ts),
            "depth_pct": episode.depth_pct,
            "failed_bounces": episode.failed_bounces,
            "failed_bounces_1pct": episode.failed_bounces_1pct,
            "recovered": episode.recovered,
            "duration_bars": episode.duration_bars,
            "max_bounce_pct": episode.max_bounce_pct,
        }
        for episode in selected
    ]


def _model_to_dict(model: ModelEvaluation) -> dict[str, Any]:
    return {
        "available": model.available,
        "reason": model.reason,
        "model_type": model.model_type,
        "samples": model.samples,
        "train_samples": model.train_samples,
        "test_samples": model.test_samples,
        "features": model.features,
        "auc": model.auc,
        "brier": model.brier,
        "log_loss": model.log_loss,
        "accuracy": model.accuracy,
        "base_rate": model.base_rate,
        "calibration": model.calibration,
        "walk_forward": model.walk_forward,
        "threshold_curve": model.threshold_curve,
        "recommended_threshold": model.recommended_threshold,
        "filtered_stats": model.filtered_stats,
        "spec": model.spec,
        "fast": model.fast,
    }


def _split_blocks(items: Sequence[Any], blocks: int) -> list[list[Any]]:
    if blocks <= 0:
        return [list(items)]
    n = len(items)
    size = n // blocks
    remainder = n % blocks
    out: list[list[Any]] = []
    start = 0
    for i in range(blocks):
        take = size + (1 if i < remainder else 0)
        out.append(list(items[start : start + take]))
        start += take
    return out


def _walk_forward(
    rule_stats: dict[str, RuleStats],
    baseline_samples: Sequence[SignalSample],
    data_start: datetime,
    data_end: datetime,
    config: AnalysisConfig,
) -> dict[str, Any]:
    times = [sample.ts for sample in baseline_samples]
    if len(times) < 30:
        return {
            "available": False,
            "reason": "Fewer than 30 candidate bars; not enough to walk forward.",
            "folds": [],
            "oos": None,
        }
    n_folds = min(config.walk_forward_folds, max(2, len(times) // 30))
    blocks = _split_blocks(times, n_folds + 1)
    folds: list[dict[str, Any]] = []
    oos_trades: list[SimulatedTrade] = []
    selected_counts: dict[str, int] = {}
    first_test_start: datetime | None = None
    last_test_end: datetime | None = None

    for fold_index in range(1, len(blocks)):
        test_block = blocks[fold_index]
        if len(test_block) < 5:
            continue
        test_start = test_block[0]
        if first_test_start is None:
            first_test_start = test_start
        if fold_index + 1 < len(blocks) and blocks[fold_index + 1]:
            test_end = blocks[fold_index + 1][0]
        else:
            test_end = data_end
        last_test_end = test_end

        best_rule: str | None = None
        best_score = -math.inf
        best_train_trades: list[SimulatedTrade] = []
        best_train_weekly = 0.0
        for rule_id, stats in rule_stats.items():
            train_trades = [
                trade
                for trade in stats.trade_list
                if trade.outcome.exit_ts < test_start
            ]
            if len(train_trades) < config.min_trades_for_rule:
                continue
            weekly = _weekly_return(train_trades, data_start, test_start)
            shrink = len(train_trades) / (len(train_trades) + 10.0)
            score = weekly * shrink
            if score > best_score:
                best_score = score
                best_rule = rule_id
                best_train_trades = train_trades
                best_train_weekly = weekly

        if best_rule is None:
            folds.append(
                {
                    "fold": fold_index,
                    "test_start": _iso(test_start),
                    "test_end": _iso(test_end),
                    "selected_rule": None,
                    "reason": "No rule had enough training trades.",
                }
            )
            continue

        selected_counts[best_rule] = selected_counts.get(best_rule, 0) + 1
        stats = rule_stats[best_rule]
        test_trades = [
            trade
            for trade in stats.trade_list
            if test_start <= trade.outcome.entry_ts < test_end
        ]
        oos_trades.extend(test_trades)
        test_weeks = max(0.5, (test_end - test_start).total_seconds() / 86_400.0 / 7.0)
        test_returns = [trade.outcome.net_return_pct for trade in test_trades]
        test_successes = sum(1 for trade in test_trades if trade.outcome.success)
        folds.append(
            {
                "fold": fold_index,
                "test_start": _iso(test_start),
                "test_end": _iso(test_end),
                "selected_rule": best_rule,
                "train_trades": len(best_train_trades),
                "train_weekly_return_pct": best_train_weekly,
                "test_trades": len(test_trades),
                "test_trades_per_week": len(test_trades) / test_weeks,
                "test_hit_rate": (
                    test_successes / len(test_trades) if test_trades else 0.0
                ),
                "test_net_ev_pct": mean(test_returns) if test_returns else 0.0,
                "test_weekly_return_pct": _weekly_return(
                    test_trades, test_start, test_end
                ),
                "test_stop_rate": (
                    mean(1.0 if t.outcome.is_stop else 0.0 for t in test_trades)
                    if test_trades
                    else 0.0
                ),
            }
        )

    oos_summary: dict[str, Any] | None = None
    if oos_trades and first_test_start is not None and last_test_end is not None:
        oos_stats = summarize_rule(
            "walk_forward_selection",
            _samples_from_trades(oos_trades),
            oos_trades,
            period_start=first_test_start,
            period_end=last_test_end,
            timeframe=config.timeframe,
        )
        oos_summary = _stats_summary(oos_stats, _rank_score(oos_stats))
    return {
        "available": bool(folds),
        "reason": "" if folds else "No fold had enough training trades.",
        "folds": folds,
        "selected_counts": selected_counts,
        "oos": oos_summary,
    }



def _episode_summary(episodes: Sequence[EpisodeRecord], weeks: float) -> dict[str, Any]:
    if not episodes:
        return {
            "count": 0,
            "per_month": 0.0,
            "fake_rebound_rate": 0.0,
            "multi_leg_rate": 0.0,
            "recovered_rate": 0.0,
            "avg_depth_pct": 0.0,
            "median_duration_bars": 0.0,
            "avg_max_bounce_pct": 0.0,
            "avg_failed_bounces": 0.0,
            "interpretation": "No dip episodes were detected in this window.",
        }
    fake = sum(1 for e in episodes if e.failed_bounces_1pct >= 1)
    multi = sum(1 for e in episodes if e.failed_bounces >= 1)
    recovered = sum(1 for e in episodes if e.recovered)
    count = len(episodes)
    weeks = max(1.0, weeks)
    interpretation = (
        f"{fake / count:.0%} of dip episodes produced at least one failed >=1% "
        "bounce before the eventual recovery. That is the fake-rebound risk the "
        "confirmation rules are designed to filter."
    )
    return {
        "count": count,
        "per_month": count / weeks * 4.33,
        "fake_rebound_rate": fake / count,
        "multi_leg_rate": multi / count,
        "recovered_rate": recovered / count,
        "avg_depth_pct": mean(e.depth_pct for e in episodes),
        "median_duration_bars": median(e.duration_bars for e in episodes),
        "avg_max_bounce_pct": mean(e.max_bounce_pct for e in episodes),
        "avg_failed_bounces": mean(e.failed_bounces for e in episodes),
        "interpretation": interpretation,
    }


def _fake_rebound_study(
    baseline_stats: RuleStats | None,
    recommended_stats: RuleStats | None,
) -> dict[str, Any] | None:
    if baseline_stats is None or recommended_stats is None:
        return None
    if recommended_stats.rule_id == "dip_close":
        return None

    def pick(stats: RuleStats, table: str, bucket: str) -> dict[str, Any] | None:
        rows = getattr(stats, table, [])
        for row in rows:
            if row.get("bucket") == bucket:
                return row
        return None

    baseline_first = pick(baseline_stats, "by_attempt", "1st attempt")
    baseline_after = pick(baseline_stats, "by_failed_bounce", "1 failed bounce")
    confirmed_first = pick(recommended_stats, "by_attempt", "1st attempt")
    confirmed_after = pick(recommended_stats, "by_failed_bounce", "1 failed bounce")
    confirmed_label = "Confirmed first attempt"

    if not baseline_first:
        return None
    if not confirmed_first:
        # Rules such as second_attempt_soft deliberately never fire on the
        # first bounce.  Compare their overall confirmed signal quality to the
        # raw first-attempt baseline instead of returning no comparison.
        confirmed_first = {
            "bucket": "all confirmed signals",
            "signals": recommended_stats.signals,
            "hit_rate": recommended_stats.signal_hit_rate,
            "ci_low": recommended_stats.signal_hit_rate_low,
            "ci_high": recommended_stats.signal_hit_rate_high,
            "net_ev_pct": recommended_stats.signal_net_ev_pct,
        }
        confirmed_label = "Confirmed rule (all attempts)"

    delta = confirmed_first["hit_rate"] - baseline_first["hit_rate"]
    sample_note = (
        f"({baseline_first['signals']} raw first-attempt signals vs "
        f"{confirmed_first['signals']} confirmed signals)"
    )
    if confirmed_label == "Confirmed rule (all attempts)":
        interpretation = (
            f"Raw first attempts hit {baseline_first['hit_rate']:.0%}; the confirmed "
            f"rule hit {confirmed_first['hit_rate']:.0%} across all attempts "
            f"({delta:+.0%}). This is consistent with the confirmation filtering "
            f"the dangerous first bounce, but the samples are not identical {sample_note}."
        )
    elif delta > 0.02:
        interpretation = (
            "Confirmation improved the first-attempt hit rate by "
            f"{delta:.0%} versus buying every dip bar. The unconfirmed first "
            f"bounce is the dangerous one {sample_note}."
        )
    elif delta < -0.02:
        interpretation = (
            "In this sample, confirmation did not improve the first-attempt hit "
            f"rate; the raw dip baseline was better {sample_note}. Treat the edge as unproven."
        )
    else:
        interpretation = (
            "Confirmation did not materially change the first-attempt hit rate in "
            f"this sample {sample_note}. Look at the after-failed-bounce rows and "
            "the walk-forward result before trusting the signal."
        )

    return {
        "baseline_first_attempt": baseline_first,
        "baseline_after_failed_bounce": baseline_after,
        "confirmed_first_attempt": confirmed_first,
        "confirmed_after_failed_bounce": confirmed_after,
        "confirmed_label": confirmed_label,
        "interpretation": interpretation,
    }



def _automation_readiness(
    *,
    qualification_status: str,
    recommended_stats: RuleStats | None,
    walk_forward: dict[str, Any],
    fake_rebound_study: dict[str, Any] | None,
    model: ModelEvaluation,
    rule_stats: dict[str, RuleStats],
    config: AnalysisConfig,
    model_filter_on: bool = False,
    filtered_eval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A plain-language answer to: could this be automated accurately?

    This is deliberately conservative.  It requires (1) a qualified uptrend,
    (2) enough sequential trades, and (3) a positive *walk-forward* estimate
    with a hit-rate confidence interval that does not straddle 50%.  A good
    in-sample rule is not enough.
    """

    oos = walk_forward.get("oos") or {}
    max_rule_trades = max((s.trades for s in rule_stats.values()), default=0)
    oos_trades = int(oos.get("trades") or 0)
    oos_hit_low = float(oos.get("hit_rate_low") or 0.0)
    oos_weekly = float(oos.get("weekly_return_pct") or 0.0)
    oos_net_ev = float(oos.get("net_ev_pct") or 0.0)
    oos_hit = float(oos.get("hit_rate") or 0.0)
    fake_lift = 0.0
    if fake_rebound_study:
        fake_lift = (
            fake_rebound_study["confirmed_first_attempt"]["hit_rate"]
            - fake_rebound_study["baseline_first_attempt"]["hit_rate"]
        )

    if qualification_status != "qualified":
        status = "not_qualified"
        summary = (
            "The daily trend/volatility checks are not qualified. The signal "
            "statistics are research-only until this becomes a confirmed uptrend."
        )
    elif oos_trades == 0:
        status = "needs_more_data"
        summary = (
            "There is no walk-forward out-of-sample evidence yet. More sequential "
            "trades (or a longer intraday cache) are needed before judging automation accuracy."
        )
    elif oos_trades < config.min_trades_for_threshold:
        status = "needs_more_data"
        summary = (
            f"Only {oos_trades} walk-forward OOS trades were available. That is too "
            "few to estimate automation accuracy with confidence."
        )
    elif oos_weekly <= 0 or oos_net_ev <= 0:
        status = "no_edge"
        summary = (
            "The walk-forward selection process was not net positive after costs. "
            "Do not automate this signal on this sample."
        )
    elif oos_hit_low < 0.5:
        status = "fragile"
        summary = (
            "The OOS edge is positive, but the hit-rate confidence interval crosses "
            "50%. Treat it as fragile and gather more data before automating."
        )
    else:
        status = "promising"
        summary = (
            "The walk-forward selection process was net positive after costs, with a "
            "hit-rate interval above 50%. This is the strongest evidence the tool can "
            "give — still historical, not a guarantee."
        )

    score = 0.0
    score += 20.0 if qualification_status == "qualified" else 0.0
    score += 25.0 if oos_weekly > 0 else 0.0
    score += 15.0 if oos_net_ev > 0 else 0.0
    score += 15.0 if oos_hit_low >= 0.5 and oos_trades else 0.0
    score += 10.0 if fake_lift > 0 else 0.0
    score += 10.0 if model.available and (model.auc or 0) >= 0.55 else 0.0
    score += 5.0 if oos_trades >= config.min_trades_for_threshold * 2 else 0.0
    if status == "not_qualified":
        score = min(score, 35.0)
    elif status == "no_edge":
        score = min(score, 40.0)
    elif status == "needs_more_data":
        score = min(score, 55.0)
    elif status == "fragile":
        score = min(score, 75.0)
    score = round(min(100.0, max(0.0, score)), 1)

    bullets: list[dict[str, Any]] = []
    if oos:
        bullets.append(
            {
                "label": "Walk-forward OOS",
                "value": (
                    f"{oos_trades} trades · {oos_hit:.0%} hit "
                    f"[{float(oos.get('hit_rate_low') or 0):.0%}–"
                    f"{float(oos.get('hit_rate_high') or 0):.0%}] · "
                    f"{oos_weekly:+.2f}%/wk"
                ),
                "tone": "good" if oos_weekly > 0 and oos_hit_low >= 0.5 else "bad",
            }
        )
    else:
        bullets.append(
            {"label": "Walk-forward OOS", "value": "Not available yet", "tone": "warn"}
        )
    if fake_rebound_study:
        bullets.append(
            {
                "label": "Fake-rebound filter",
                "value": (
                    f"{fake_rebound_study['confirmed_first_attempt']['hit_rate']:.0%} "
                    f"{fake_rebound_study.get('confirmed_label', 'confirmed')} vs "
                    f"{fake_rebound_study['baseline_first_attempt']['hit_rate']:.0%} "
                    f"raw first attempt ({fake_lift:+.0%})"
                ),
                "tone": "good" if fake_lift > 0 else "bad",
            }
        )
    if recommended_stats:
        bullets.append(
            {
                "label": "Time in market",
                "value": (
                    f"median {recommended_stats.median_holding_minutes:.0f} market min · "
                    f"{recommended_stats.trades_per_week:.2f} trades/wk"
                ),
                "tone": "neutral",
            }
        )
        bullets.append(
            {
                "label": "In-sample rule",
                "value": (
                    f"{recommended_stats.trades} trades · {recommended_stats.hit_rate:.0%} hit · "
                    f"{recommended_stats.weekly_return_pct:+.2f}%/wk"
                ),
                "tone": "neutral",
            }
        )
    if model_filter_on and filtered_eval:
        bullets.append(
            {
                "label": "Model filter (held-out)",
                "value": (
                    f"{filtered_eval.get('trades', 0)} trades · "
                    f"{float(filtered_eval.get('hit_rate') or 0):.0%} hit · "
                    f"{float(filtered_eval.get('weekly_return_pct') or 0):+.2f}%/wk"
                ),
                "tone": "good",
            }
        )
    bullets.append(
        {
            "label": "Probability model",
            "value": (
                f"AUC {model.auc:.3f} · Brier {model.brier:.3f} · "
                f"filter {'on' if model_filter_on else 'off'}"
                if model.available and model.auc is not None and model.brier is not None
                else "unavailable / insufficient samples"
            ),
            "tone": "good" if model.available and (model.auc or 0) >= 0.55 else "warn",
        }
    )

    return {
        "status": status,
        "score": score,
        "summary": summary,
        "bullets": bullets,
        "metrics": {
            "oos_trades": oos_trades,
            "oos_hit_rate": oos_hit,
            "oos_hit_rate_low": oos_hit_low,
            "oos_hit_rate_high": float(oos.get("hit_rate_high") or 0.0),
            "oos_net_ev_pct": oos_net_ev,
            "oos_weekly_return_pct": oos_weekly,
            "oos_max_drawdown_pct": float(oos.get("max_drawdown_pct") or 0.0),
            "median_holding_minutes": (
                recommended_stats.median_holding_minutes if recommended_stats else 0.0
            ),
            "trades_per_week": (
                recommended_stats.trades_per_week if recommended_stats else 0.0
            ),
            "fake_rebound_lift": fake_lift,
            "model_auc": model.auc if model.available else None,
            "model_brier": model.brier if model.available else None,
            "max_rule_trades": max_rule_trades,
        },
    }


def _data_summary(
    *,
    config: AnalysisConfig,
    mode: str,
    daily_bars: Sequence[Bar],
    intraday_bars: Sequence[Bar],
    series: FeatureSeries,
    data_info: dict[str, Any] | None,
) -> dict[str, Any]:
    daily_start = daily_bars[0].ts if daily_bars else None
    daily_end = daily_bars[-1].ts if daily_bars else None
    intraday_start = intraday_bars[0].ts if intraday_bars else None
    intraday_end = intraday_bars[-1].ts if intraday_bars else None
    quality: dict[str, Any] = {}
    if mode != "1d" and series.rows:
        sessions = [session_date(bar) for bar in intraday_bars]
        counts: dict[date, int] = {}
        for session in sessions:
            counts[session] = counts.get(session, 0) + 1
        expected = config.bars_per_day
        quality = {
            "sessions": len(counts),
            "median_bars_per_session": median(counts.values()) if counts else 0,
            "min_bars_per_session": min(counts.values()) if counts else 0,
            "max_bars_per_session": max(counts.values()) if counts else 0,
            "expected_bars_per_session": expected,
            "coverage_pct": (
                min(100.0, median(counts.values()) / expected * 100.0)
                if counts
                else 0.0
            ),
        }
    return {
        "mode": mode,
        "timeframe": config.timeframe,
        "requested_timeframe": (data_info or {}).get("requested_timeframe", config.timeframe),
        "daily": {
            "bars": len(daily_bars),
            "start": _iso(daily_start),
            "end": _iso(daily_end),
            "source": (data_info or {}).get("daily_source"),
        },
        "intraday": {
            "bars": len(intraday_bars),
            "start": _iso(intraday_start),
            "end": _iso(intraday_end),
            "source": (data_info or {}).get("intraday_source"),
            "used": mode != "1d",
        },
        "quality": quality,
        "coverage": (data_info or {}).get("coverage", {}),
    }


def build_profile(
    *,
    symbol: str,
    daily_bars: list[Bar],
    intraday_bars: list[Bar] | None = None,
    config: AnalysisConfig | None = None,
    data_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct the full analysis JSON consumed by the API/UI."""

    config = config or AnalysisConfig()
    symbol = symbol.upper().strip()
    daily_bars = normalize_bars(daily_bars, timeframe="1d")
    intraday_bars = normalize_bars(intraday_bars or [], timeframe=config.timeframe) if intraday_bars else []
    if not daily_bars and intraday_bars:
        daily_bars = resample_daily(intraday_bars)

    warnings: list[str] = []
    intraday_ok = (
        config.timeframe != "1d"
        and len(intraday_bars) >= config.min_intraday_bars
    )
    mode = config.timeframe if intraday_ok else "1d"
    if config.timeframe != "1d" and not intraday_ok:
        warnings.append(
            "Intraday history is insufficient for the requested timeframe; "
            "the profile fell back to daily confirmation bars."
        )
    effective_config = config.with_overrides(timeframe=mode)
    if not daily_bars:
        return {
            "meta": {
                "symbol": symbol,
                "generated_at": _iso(datetime.now(timezone.utc)),
                "engine_version": ENGINE_VERSION,
                "config_hash": config.hash,
                "effective_config_hash": effective_config.hash,
                "mode": mode,
                "timeframe": effective_config.timeframe,
                "fast_horizon_label": effective_config.fast_horizon_label,
                "bars_analyzed": 0,
                "candidate_bars": 0,
                "episodes": 0,
                "disclaimer": DISCLAIMER,
                "error": "no_data",
            },
            "config": effective_config.as_dict(),
            "requested_config": config.as_dict(),
            "data": {},
            "qualification": {"status": "reject", "score": 0, "reasons": []},
            "daily": {},
            "episodes": [],
            "episode_summary": _episode_summary([], 1.0),
            "automation_readiness": {
                "status": "not_qualified",
                "score": 0.0,
                "summary": "No data is available for this symbol.",
                "bullets": [],
                "metrics": {},
            },
            "rules": [],
            "recommended": None,
            "model": {"available": False, "reason": "No data."},
            "walk_forward": {"available": False, "reason": "No data.", "folds": []},
            "attempt_analysis": None,
            "fake_rebound_study": None,
            "signal_read": {"state": "no_data", "detail": "No bars available."},
            "trades": [],
            "equity_curve": [],
            "warnings": ["No bars available for this symbol."],
        }

    daily_profile = build_daily_profile(daily_bars, config)
    warnings.extend(daily_profile.get("warnings", []))

    if mode == "1d":
        daily_context = build_daily_contexts(daily_bars, include_current_day=True)
        analysis_bars = daily_bars
    else:
        sessions = sorted({session_date(bar) for bar in intraday_bars})
        daily_context = build_daily_contexts(
            daily_bars, intraday_sessions=sessions, include_current_day=False
        )
        analysis_bars = intraday_bars

    series = build_features(
        analysis_bars,
        effective_config,
        daily_context=daily_context,
        symbol=symbol,
    )
    rows = series.rows
    if not rows:
        return {
            "meta": {
                "symbol": symbol,
                "generated_at": _iso(datetime.now(timezone.utc)),
                "engine_version": ENGINE_VERSION,
                "config_hash": config.hash,
                "effective_config_hash": effective_config.hash,
                "mode": mode,
                "timeframe": effective_config.timeframe,
                "fast_horizon_label": effective_config.fast_horizon_label,
                "bars_analyzed": len(analysis_bars),
                "candidate_bars": 0,
                "episodes": 0,
                "disclaimer": DISCLAIMER,
                "error": "no_rows",
            },
            "config": effective_config.as_dict(),
            "requested_config": config.as_dict(),
            "data": _data_summary(
                config=effective_config,
                mode=mode,
                daily_bars=daily_bars,
                intraday_bars=intraday_bars,
                series=series,
                data_info=data_info,
            ),
            "qualification": daily_profile.get("qualification", {}),
            "daily": daily_profile,
            "episodes": [],
            "episode_summary": _episode_summary([], 1.0),
            "automation_readiness": {
                "status": "not_qualified",
                "score": 0.0,
                "summary": "Bars were available but no feature rows could be built.",
                "bullets": [],
                "metrics": {},
            },
            "rules": [],
            "recommended": None,
            "model": {"available": False, "reason": "No feature rows."},
            "walk_forward": {
                "available": False,
                "reason": "No feature rows.",
                "folds": [],
            },
            "attempt_analysis": None,
            "fake_rebound_study": None,
            "signal_read": {"state": "no_data", "detail": "No feature rows."},
            "trades": [],
            "equity_curve": [],
            "warnings": warnings + ["No feature rows could be built."],
        }

    outcomes = label_all(analysis_bars, rows, effective_config)
    rules = available_rules(effective_config)
    period_start = analysis_bars[0].ts
    period_end = analysis_bars[-1].ts

    rule_stats: dict[str, RuleStats] = {}
    samples_by_rule: dict[str, list[SignalSample]] = {}
    for rule in rules:
        samples = collect_samples(rule, rows, outcomes, effective_config)
        trades = simulate_rule_trades(rule, rows, outcomes, effective_config)
        stats = summarize_rule(
            rule.id,
            samples,
            trades,
            period_start=period_start,
            period_end=period_end,
            timeframe=effective_config.timeframe,
        )
        rule_stats[rule.id] = stats
        samples_by_rule[rule.id] = samples

    eligible = [
        stats
        for stats in rule_stats.values()
        if stats.trades >= effective_config.min_trades_for_rule
    ]
    ranked = sorted(
        rule_stats.values(),
        key=_rank_score if eligible else lambda s: (s.trades, s.signals),
        reverse=True,
    )
    recommended_stats = ranked[0] if eligible else None
    recommended_rule = (
        next((r for r in rules if r.id == recommended_stats.rule_id), None)
        if recommended_stats
        else None
    )

    baseline_samples = samples_by_rule.get("dip_close", [])
    walk_forward = _walk_forward(
        rule_stats, baseline_samples, period_start, period_end, effective_config
    )

    model = ModelEvaluation(available=False, reason="No eligible signal rule.")
    recommended_samples: list[SignalSample] = []
    if recommended_rule is not None:
        recommended_samples = samples_by_rule.get(recommended_rule.id, [])
        valid_samples = [s for s in recommended_samples if s.outcome is not None]
        model = train_model(valid_samples, effective_config)

    if model.available and model.spec and recommended_rule is not None:
        for stats in rule_stats.values():
            for trade in stats.trade_list:
                if trade.features is not None:
                    trade.probability = predict_probability(model.spec, trade.features)
                    if model.fast and model.fast.get("spec"):
                        trade.probability_fast = predict_probability(
                            model.fast["spec"], trade.features  # type: ignore[arg-type]
                        )

    use_model_filter = False
    filtered_summary: dict[str, Any] | None = None
    unfiltered_oos_summary: dict[str, Any] | None = None
    filter_eval: dict[str, Any] = {}
    if (
        model.available
        and model.oos_indices
        and recommended_rule is not None
    ):
        valid_samples = [s for s in recommended_samples if s.outcome is not None]
        oos_samples = [
            valid_samples[i] for i in model.oos_indices if i < len(valid_samples)
        ]
        oos_probs = list(model.oos_probabilities[: len(oos_samples)])
        if oos_samples:
            split = int(len(oos_samples) * 0.60)
            use_split = split >= 10 and len(oos_samples) - split >= 5
            if use_split:
                select_samples = oos_samples[:split]
                select_probs = oos_probs[:split]
                eval_samples = oos_samples[split:]
                eval_probs = oos_probs[split:]
                select_end = max(
                    (
                        s.outcome.exit_ts
                        for s in select_samples
                        if s.outcome is not None
                    ),
                    default=select_samples[-1].ts,
                )
                curve = threshold_curve(
                    select_samples,
                    select_probs,
                    period_start=select_samples[0].ts,
                    period_end=select_end,
                    min_trades=effective_config.min_trades_for_threshold,
                )
                if curve:
                    eligible_rows = [
                        row for row in curve if float(row.get("hit_rate", 0)) >= 0.5
                    ]
                    best = max(
                        eligible_rows or curve,
                        key=lambda row: (
                            float(row.get("weekly_return_pct", -100))
                            - 0.15 * abs(float(row.get("max_drawdown_pct", 0)))
                        ),
                    )
                    threshold = float(best["threshold"])
                    model.recommended_threshold = threshold
                    model.threshold_curve = curve
                    eval_end = max(
                        (
                            s.outcome.exit_ts
                            for s in eval_samples
                            if s.outcome is not None
                        ),
                        default=eval_samples[-1].ts,
                    )
                    filtered_trades = simulate_with_probabilities(
                        eval_samples,
                        eval_probs,
                        threshold=threshold,
                        rule_id=recommended_rule.id,
                    )
                    unfiltered_trades = simulate_with_probabilities(
                        eval_samples,
                        [1.0] * len(eval_samples),
                        threshold=0.0,
                        rule_id=recommended_rule.id,
                    )
                    filtered_stats = summarize_rule(
                        "model_filter",
                        _samples_from_trades(filtered_trades),
                        filtered_trades,
                        period_start=eval_samples[0].ts,
                        period_end=eval_end,
                        timeframe=effective_config.timeframe,
                    )
                    unfiltered_stats = summarize_rule(
                        "unfiltered_oos",
                        _samples_from_trades(unfiltered_trades),
                        unfiltered_trades,
                        period_start=eval_samples[0].ts,
                        period_end=eval_end,
                        timeframe=effective_config.timeframe,
                    )
                    filtered_summary = _stats_summary(
                        filtered_stats, _rank_score(filtered_stats)
                    )
                    unfiltered_oos_summary = _stats_summary(
                        unfiltered_stats, _rank_score(unfiltered_stats)
                    )
                    use_model_filter = bool(
                        filtered_stats.trades
                        >= effective_config.min_trades_for_threshold
                        and filtered_stats.weekly_return_pct
                        > unfiltered_stats.weekly_return_pct
                        and filtered_stats.hit_rate >= unfiltered_stats.hit_rate
                    )
                    filter_eval = {
                        "method": "60/40 chronological split on walk-forward OOS predictions",
                        "selection_samples": len(select_samples),
                        "eval_samples": len(eval_samples),
                        "selection_threshold": threshold,
                    }
            if not filter_eval:
                # Not enough held-out data for a split.  Fall back to the full
                # OOS set and label it clearly.
                threshold = model.recommended_threshold
                filtered_trades = simulate_with_probabilities(
                    oos_samples,
                    oos_probs,
                    threshold=threshold,
                    rule_id=recommended_rule.id,
                )
                unfiltered_trades = simulate_with_probabilities(
                    oos_samples,
                    [1.0] * len(oos_samples),
                    threshold=0.0,
                    rule_id=recommended_rule.id,
                )
                oos_period_end = max(
                    (
                        s.outcome.exit_ts
                        for s in oos_samples
                        if s.outcome is not None
                    ),
                    default=oos_samples[-1].ts,
                )
                filtered_stats = summarize_rule(
                    "model_filter",
                    _samples_from_trades(filtered_trades),
                    filtered_trades,
                    period_start=oos_samples[0].ts,
                    period_end=oos_period_end,
                    timeframe=effective_config.timeframe,
                )
                unfiltered_stats = summarize_rule(
                    "unfiltered_oos",
                    _samples_from_trades(unfiltered_trades),
                    unfiltered_trades,
                    period_start=oos_samples[0].ts,
                    period_end=oos_period_end,
                    timeframe=effective_config.timeframe,
                )
                filtered_summary = _stats_summary(
                    filtered_stats, _rank_score(filtered_stats)
                )
                unfiltered_oos_summary = _stats_summary(
                    unfiltered_stats, _rank_score(unfiltered_stats)
                )
                use_model_filter = bool(
                    filtered_stats.trades >= effective_config.min_trades_for_threshold
                    and filtered_stats.weekly_return_pct
                    > unfiltered_stats.weekly_return_pct
                    and filtered_stats.hit_rate >= unfiltered_stats.hit_rate
                )
                filter_eval = {
                    "method": "full OOS (not enough data for a held-out split)",
                    "selection_samples": len(oos_samples),
                    "eval_samples": len(oos_samples),
                    "selection_threshold": threshold,
                }

    rank_scores = {rule_id: _rank_score(stats) for rule_id, stats in rule_stats.items()}
    rule_summaries: list[dict[str, Any]] = []
    for stats in sorted(rule_stats.values(), key=lambda s: rank_scores[s.rule_id], reverse=True):
        rule = next((r for r in rules if r.id == stats.rule_id), None)
        summary = _stats_summary(stats, rank_scores[stats.rule_id])
        if rule:
            summary.update(
                {
                    "name": rule.name,
                    "description": rule.description,
                    "family": rule.family,
                    "confirmations": list(rule.confirmations),
                }
            )
        rule_summaries.append(summary)

    recommended_summary = (
        _stats_summary(
            recommended_stats, rank_scores.get(recommended_stats.rule_id, 0.0)
        )
        if recommended_stats
        else None
    )
    if recommended_summary and recommended_rule:
        recommended_summary.update(
            {
                "name": recommended_rule.name,
                "description": recommended_rule.description,
                "family": recommended_rule.family,
                "confirmations": list(recommended_rule.confirmations),
            }
        )

    recommended_trades: list[SimulatedTrade] = (
        list(recommended_stats.trade_list) if recommended_stats else []
    )
    response_trades = recommended_trades[-500:]
    trades_json = [_trade_to_dict(trade) for trade in response_trades]

    signal_read = build_signal_read(
        rows,
        rules,
        recommended_rule,
        model.spec if model.available else None,
        model.fast.get("spec") if model.available and model.fast else None,
        effective_config,
    )

    if model.available:
        model_dict = _model_to_dict(model)
        model_dict["filtered_stats"] = filtered_summary or {}
        model_dict["unfiltered_oos_stats"] = unfiltered_oos_summary or {}
        model_dict["use_filter"] = use_model_filter
        model_dict["filter_eval"] = filter_eval
    else:
        model_dict = _model_to_dict(model)

    if not eligible:
        warnings.append(
            "No signal rule produced at least "
            f"{effective_config.min_trades_for_rule} sequential trades. The rule "
            "comparison is exploratory only; there is no recommended signal."
        )
    if not model.available:
        warnings.append(
            "Probability model unavailable: " + (model.reason or "insufficient samples.")
        )
    if daily_profile.get("qualification", {}).get("status") != "qualified":
        warnings.append(
            "Daily qualification is "
            f"{daily_profile.get('qualification', {}).get('status', 'unknown')}; "
            "treat this as a research candidate, not a confirmed uptrend."
        )
    if recommended_rule and recommended_rule.id == "dip_close":
        warnings.append(
            "No confirmation rule beat the buy-every-dip baseline in this sample; "
            "the signal edge is unproven."
        )
    if recommended_stats and recommended_stats.hit_rate_low < 0.5 and recommended_stats.trades:
        warnings.append(
            "The 95% confidence interval on the recommended rule's hit rate crosses 50%."
        )
    if mode != "1d" and len({session_date(b) for b in intraday_bars}) < 20:
        warnings.append(
            "Fewer than 20 intraday sessions are cached; results will improve as history accumulates."
        )
    warnings.extend((data_info or {}).get("warnings", []))

    attempt_analysis = None
    if recommended_stats:
        attempt_analysis = {
            "rule_id": recommended_stats.rule_id,
            "by_attempt": recommended_stats.by_attempt,
            "by_failed_bounce": recommended_stats.by_failed_bounce,
        }
        first = next(
            (row for row in recommended_stats.by_attempt if row["bucket"] == "1st attempt"),
            None,
        )
        later = next(
            (
                row
                for row in recommended_stats.by_attempt
                if row["bucket"] in {"2nd attempt", "3rd+ attempt"}
            ),
            None,
        )
        if first and later:
            attempt_analysis["interpretation"] = (
                "Waiting for a later attempt changed the hit rate from "
                f"{first['hit_rate']:.0%} to {later['hit_rate']:.0%}."
            )
        elif first:
            attempt_analysis["interpretation"] = (
                "Most signals are first attempts; the first-bounce hit rate is "
                f"{first['hit_rate']:.0%}."
            )

    selection_reason = "No signal rule met the minimum trade count."
    if recommended_stats and recommended_rule:
        selection_reason = (
            f"{recommended_rule.name} ranked highest after shrinking for sample size "
            f"and penalising drawdown: {recommended_stats.weekly_return_pct:.2f}%/week, "
            f"{recommended_stats.hit_rate:.0%} hit rate, "
            f"{recommended_stats.trades} trades, "
            f"{recommended_stats.max_drawdown_pct:.1f}% max drawdown."
        )
        if not eligible:
            selection_reason += " It did not meet the minimum trade count."

    recommended = None
    if recommended_stats and recommended_rule:
        recommended = {
            "rule_id": recommended_rule.id,
            "name": recommended_rule.name,
            "description": recommended_rule.description,
            "family": recommended_rule.family,
            "confirmations": list(recommended_rule.confirmations),
            "stats": recommended_summary,
            "walk_forward_oos": walk_forward.get("oos"),
            "selection_reason": selection_reason,
            "use_model_filter": use_model_filter,
            "threshold": model.recommended_threshold if use_model_filter else None,
            "filtered_stats": filtered_summary or {},
            "attempt_analysis": attempt_analysis,
        }

    data_summary = _data_summary(
        config=effective_config,
        mode=mode,
        daily_bars=daily_bars,
        intraday_bars=intraday_bars,
        series=series,
        data_info=data_info,
    )
    data_summary["requested_timeframe"] = config.timeframe
    data_summary["fallback"] = mode != config.timeframe

    weeks = max(
        1.0, (period_end - period_start).total_seconds() / 86_400.0 / 7.0
    )
    episode_summary = _episode_summary(list(series.episodes), weeks)
    fake_rebound_study = _fake_rebound_study(
        rule_stats.get("dip_close"), recommended_stats
    )
    readiness = _automation_readiness(
        qualification_status=daily_profile.get("qualification", {}).get(
            "status", "reject"
        ),
        recommended_stats=recommended_stats,
        walk_forward=walk_forward,
        fake_rebound_study=fake_rebound_study,
        model=model,
        rule_stats=rule_stats,
        config=effective_config,
        model_filter_on=use_model_filter,
        filtered_eval=filtered_summary,
    )
    profile = {
        "meta": {
            "symbol": symbol,
            "generated_at": _iso(datetime.now(timezone.utc)),
            "engine_version": ENGINE_VERSION,
            "config_hash": config.hash,
            "effective_config_hash": effective_config.hash,
            "mode": mode,
            "timeframe": effective_config.timeframe,
            "fast_horizon_label": effective_config.fast_horizon_label,
            "bars_analyzed": len(analysis_bars),
            "candidate_bars": sum(
                1 for row in rows if is_candidate_bar(row, effective_config)
            ),
            "episodes": len(series.episodes),
            "disclaimer": DISCLAIMER,
        },
        "config": effective_config.as_dict(),
        "requested_config": config.as_dict(),
        "data": data_summary,
        "qualification": daily_profile.get("qualification", {}),
        "daily": daily_profile,
        "episodes": _episodes_to_dict(series.episodes),
        "episode_summary": episode_summary,
        "automation_readiness": readiness,
        "rules": rule_summaries,
        "recommended": recommended,
        "model": model_dict,
        "walk_forward": walk_forward,
        "attempt_analysis": attempt_analysis,
        "fake_rebound_study": fake_rebound_study,
        "signal_read": signal_read,
        "trades": trades_json,
        "equity_curve": equity_curve(response_trades),
        "warnings": list(dict.fromkeys(warnings)),
    }
    return _json_safe(profile)
