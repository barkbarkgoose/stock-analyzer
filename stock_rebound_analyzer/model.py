"""A small, transparent probability model for the buy signal.

The model answers: *given the dip/episode context at the signal bar, what is
the probability that +target is hit before the stop within the holding window?*
It is intentionally a regularised logistic regression with a handful of
features.  More powerful models are easy to add later, but with a few hundred
samples per symbol a simple, calibrated model is the honest choice.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Sequence

from .config import AnalysisConfig
from .stats import (
    auc_score,
    brier_score,
    calibration_table,
    threshold_curve,
)
from .types import FeatureRow, ModelEvaluation, SignalSample

# Keep this list short.  Every extra feature makes the walk-forward estimate
# noisier, and most of the signal is in the episode state/confirmation context.
FEATURE_NAMES: tuple[str, ...] = (
    "episode_depth_pct",
    "drawdown_from_high_pct",
    "drawdown_from_prior_close_pct",
    "runup_from_low_pct",
    "bars_since_episode_low",
    "failed_bounces_1pct",
    "volume_ratio20",
    "rsi14",
    "atr_pct",
    "price_vs_vwap_pct",
    "higher_low",
    "close_above_prior_swing_high",
    "minutes_since_open_norm",
    "daily_trend_score",
    "gap_pct",
    "daily_last_return_pct",
    "daily_two_day_return_pct",
    "daily_last_range_pct",
)


def _feature_value(row: FeatureRow, name: str) -> float:
    if name == "rsi14":
        return float(row.rsi14 if row.rsi14 is not None else 50.0)
    if name == "minutes_since_open_norm":
        return row.minutes_since_open / 390.0
    if name == "higher_low":
        return 1.0 if row.higher_low else 0.0
    if name == "close_above_prior_swing_high":
        return 1.0 if row.close_above_prior_swing_high else 0.0
    value = getattr(row, name, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def feature_matrix(samples: Sequence[SignalSample]) -> list[list[float]]:
    return [
        [_feature_value(sample.features, name) for name in FEATURE_NAMES]
        for sample in samples
    ]


def _fit_logistic(
    x: Any, y: Any
) -> tuple[list[float], float, list[float], list[float]] | None:
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
    except Exception:
        return None

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=int)
    if x.ndim != 2 or len(x) == 0 or len(set(y.tolist())) < 2:
        return None
    means = x.mean(axis=0)
    scales = x.std(axis=0)
    scales[scales == 0] = 1.0
    z = (x - means) / scales
    z = np.clip(z, -5.0, 5.0)
    model = LogisticRegression(
        C=0.5,
        solver="lbfgs",
        max_iter=2000,
        random_state=7,
    )
    model.fit(z, y)
    coef = model.coef_[0].astype(float).tolist()
    intercept = float(model.intercept_[0])
    return coef, intercept, means.astype(float).tolist(), scales.astype(float).tolist()


def predict_probability(spec: dict[str, Any], row: FeatureRow) -> float | None:
    try:
        coefficients = spec["coefficients"]
        means = spec["means"]
        scales = spec["scales"]
        intercept = float(spec["intercept"])
        clip = float(spec.get("clip", 5.0))
    except (KeyError, TypeError, ValueError):
        return None
    logit = intercept
    for name, coef, mean_value, scale in zip(
        FEATURE_NAMES, coefficients, means, scales
    ):
        value = _feature_value(row, name)
        z = (value - float(mean_value)) / (float(scale) or 1.0)
        z = max(-clip, min(clip, z))
        logit += float(coef) * z
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    exp_logit = math.exp(logit)
    return exp_logit / (1.0 + exp_logit)


def _metrics(
    labels: list[bool], probabilities: list[float]
) -> dict[str, Any]:
    if not labels:
        return {}
    accuracy = mean(
        1.0 if (p >= 0.5) == label else 0.0
        for p, label in zip(probabilities, labels)
    )
    log_loss = None
    try:
        log_loss = mean(
            -(
                math.log(max(1e-12, p)) if label else math.log(max(1e-12, 1.0 - p))
            )
            for p, label in zip(probabilities, labels)
        )
    except ValueError:
        log_loss = None
    return {
        "samples": len(labels),
        "base_rate": mean(1.0 if label else 0.0 for label in labels),
        "auc": auc_score(labels, probabilities),
        "brier": brier_score(labels, probabilities),
        "log_loss": log_loss,
        "accuracy": accuracy,
        "calibration": calibration_table(labels, probabilities),
    }


def _train_bundle(
    samples: Sequence[SignalSample],
    labels: Sequence[bool],
    config: AnalysisConfig,
) -> dict[str, Any]:
    """Fit a walk-forward evaluation plus a full-history deployment model."""

    n = len(samples)
    if n < config.min_samples_for_model:
        return {
            "available": False,
            "reason": f"Need at least {config.min_samples_for_model} signals (have {n}).",
        }
    positives = sum(1 for label in labels if label)
    negatives = n - positives
    if positives < 5 or negatives < 5:
        return {
            "available": False,
            "reason": (
                "Need at least 5 successes and 5 failures to fit a probability model "
                f"(have {positives}/{negatives})."
            ),
        }

    try:
        import numpy as np
    except Exception:
        return {"available": False, "reason": "numpy is not installed."}

    x_all = np.asarray(feature_matrix(samples), dtype=float)
    y_all = np.asarray([1 if label else 0 for label in labels], dtype=int)

    # Expanding-window walk-forward with an outcome-based embargo.  A sample is
    # only in the training set if its trade has already exited before the test
    # block starts, which prevents label leakage.
    n_splits = min(
        config.walk_forward_folds,
        max(2, n // 15),
    )
    blocks = np.array_split(np.arange(n), n_splits + 1)
    oos_indices: list[int] = []
    oos_probs: list[float] = []
    folds: list[dict[str, Any]] = []

    for block in blocks[1:]:
        if len(block) == 0:
            continue
        test_start_index = int(block[0])
        test_start_ts = samples[test_start_index].ts
        train_indices = [
            i
            for i in range(test_start_index)
            if samples[i].outcome is not None
            and samples[i].outcome.exit_ts < test_start_ts  # type: ignore[union-attr]
        ]
        test_indices = [int(i) for i in block]
        if len(train_indices) < 15 or len(test_indices) < 5:
            continue
        train_labels = [labels[i] for i in train_indices]
        if len(set(train_labels)) < 2:
            continue
        fitted = _fit_logistic(x_all[train_indices], y_all[train_indices])
        if fitted is None:
            continue
        coef, intercept, means, scales = fitted
        spec = {
            "features": list(FEATURE_NAMES),
            "coefficients": coef,
            "intercept": intercept,
            "means": means,
            "scales": scales,
            "clip": 5.0,
        }
        probs = [
            predict_probability(spec, samples[i].features) or 0.5
            for i in test_indices
        ]
        test_labels = [labels[i] for i in test_indices]
        fold_metrics = _metrics(test_labels, probs)
        folds.append(
            {
                "fold": len(folds) + 1,
                "test_start": test_start_ts.isoformat(),
                "train_samples": len(train_indices),
                "test_samples": len(test_indices),
                **{
                    key: fold_metrics.get(key)
                    for key in ("auc", "brier", "base_rate", "accuracy")
                },
            }
        )
        oos_indices.extend(test_indices)
        oos_probs.extend(probs)

    # Full-history model for live use.
    full_fit = _fit_logistic(x_all, y_all)
    if full_fit is None:
        return {
            "available": False,
            "reason": "Could not fit the logistic model.",
        }
    coef, intercept, means, scales = full_fit
    full_spec = {
        "features": list(FEATURE_NAMES),
        "coefficients": coef,
        "intercept": intercept,
        "means": means,
        "scales": scales,
        "clip": 5.0,
        "samples": n,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    feature_rows = [
        {
            "name": name,
            "coefficient": float(coef[i]),
            "odds_ratio": math.exp(float(coef[i])),
            "importance": abs(float(coef[i])),
        }
        for i, name in enumerate(FEATURE_NAMES)
    ]
    feature_rows.sort(key=lambda item: float(item["importance"]), reverse=True)

    result: dict[str, Any] = {
        "available": True,
        "reason": "",
        "samples": n,
        "positives": positives,
        "negatives": negatives,
        "features": feature_rows,
        "spec": full_spec,
        "walk_forward": folds,
        "train_samples": n,
        "test_samples": len(oos_indices),
    }
    if oos_indices:
        oos_labels = [labels[i] for i in oos_indices]
        metrics = _metrics(oos_labels, oos_probs)
        result.update(
            {
                "auc": metrics.get("auc"),
                "brier": metrics.get("brier"),
                "log_loss": metrics.get("log_loss"),
                "accuracy": metrics.get("accuracy"),
                "base_rate": metrics.get("base_rate"),
                "calibration": metrics.get("calibration", []),
                "oos_samples": len(oos_indices),
            }
        )
        oos_samples = [samples[i] for i in oos_indices]
        if oos_samples:
            curve = threshold_curve(
                oos_samples,
                oos_probs,
                period_start=oos_samples[0].ts,
                period_end=oos_samples[-1].outcome.exit_ts
                if oos_samples[-1].outcome
                else oos_samples[-1].ts,
                min_trades=config.min_trades_for_threshold,
            )
            result["threshold_curve"] = curve
            if curve:
                eligible = [
                    item
                    for item in curve
                    if float(item.get("hit_rate", 0)) >= 0.5
                ]
                pool = eligible or curve
                best = max(
                    pool,
                    key=lambda item: (
                        float(item.get("weekly_return_pct", -100))
                        - 0.15 * abs(float(item.get("max_drawdown_pct", 0)))
                    ),
                )
                result["recommended_threshold"] = float(best["threshold"])
                result["filtered_stats"] = best
                result["oos_probabilities"] = list(oos_probs)
                result["oos_indices"] = list(oos_indices)
            else:
                result["recommended_threshold"] = config.model_threshold
                result["filtered_stats"] = {}
        else:
            result["recommended_threshold"] = config.model_threshold
    else:
        result["recommended_threshold"] = config.model_threshold
    return result


def train_model(
    samples: Sequence[SignalSample], config: AnalysisConfig
) -> ModelEvaluation:
    valid = [s for s in samples if s.outcome is not None]
    if not valid:
        return ModelEvaluation(
            available=False, reason="No labelled signals to train on."
        )
    labels = [s.success for s in valid]
    primary = _train_bundle(valid, labels, config)
    if not primary.get("available"):
        return ModelEvaluation(
            available=False,
            reason=str(primary.get("reason") or "Model unavailable."),
            samples=len(valid),
        )

    fast_labels = [s.fast_success for s in valid]
    fast = _train_bundle(valid, fast_labels, config)
    fast_public = None
    if fast.get("available"):
        fast_public = {
            "samples": fast.get("samples"),
            "positives": fast.get("positives"),
            "negatives": fast.get("negatives"),
            "auc": fast.get("auc"),
            "brier": fast.get("brier"),
            "base_rate": fast.get("base_rate"),
            "calibration": fast.get("calibration", []),
            "walk_forward": fast.get("walk_forward", []),
            "spec": fast.get("spec"),
        }

    evaluation = ModelEvaluation(
        available=True,
        model_type="logistic_regression",
        samples=len(valid),
        train_samples=int(primary.get("train_samples") or 0),
        test_samples=int(primary.get("test_samples") or 0),
        features=list(primary.get("features") or []),
        auc=primary.get("auc"),
        brier=primary.get("brier"),
        log_loss=primary.get("log_loss"),
        accuracy=primary.get("accuracy"),
        base_rate=float(primary.get("base_rate") or 0.0),
        calibration=list(primary.get("calibration") or []),
        walk_forward=list(primary.get("walk_forward") or []),
        threshold_curve=list(primary.get("threshold_curve") or []),
        recommended_threshold=float(
            primary.get("recommended_threshold") or config.model_threshold
        ),
        filtered_stats=dict(primary.get("filtered_stats") or {}),
        spec=primary.get("spec"),
        fast=fast_public,
        oos_indices=list(primary.get("oos_indices") or []),
        oos_probabilities=list(primary.get("oos_probabilities") or []),
    )
    return evaluation
