from __future__ import annotations

from datetime import datetime, timezone

from stock_rebound_analyzer.model import FEATURE_NAMES, predict_probability
from stock_rebound_analyzer.types import FeatureRow


def test_predict_probability_with_zero_coefficients() -> None:
    row = FeatureRow(
        index=0,
        ts=datetime(2026, 1, 5, tzinfo=timezone.utc),
        session=datetime(2026, 1, 5).date(),
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1000,
    )
    spec = {
        "features": [],
        "coefficients": [0.0] * len(FEATURE_NAMES),
        "means": [0.0] * len(FEATURE_NAMES),
        "scales": [1.0] * len(FEATURE_NAMES),
        "intercept": 0.0,
        "clip": 5.0,
    }
    assert predict_probability(spec, row) == 0.5
