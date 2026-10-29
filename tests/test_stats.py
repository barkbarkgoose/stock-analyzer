from __future__ import annotations

import pytest

from stock_rebound_analyzer.stats import (
    auc_score,
    brier_score,
    calibration_table,
    geometric_total,
    quantile,
    wilson_interval,
)


def test_wilson_interval_is_sane() -> None:
    low, high = wilson_interval(5, 10)
    assert 0 < low < 0.5 < high < 1
    assert wilson_interval(0, 0) == (0.0, 0.0)
    low, high = wilson_interval(10, 10)
    assert low > 0.5 and high == 1.0


def test_auc() -> None:
    assert auc_score([False, False, True, True], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert auc_score([False, False, True, True], [0.9, 0.8, 0.2, 0.1]) == 0.0
    assert auc_score([False, True], [0.5, 0.5]) == 0.5
    assert auc_score([True, True], [0.1, 0.2]) is None


def test_brier_and_calibration() -> None:
    assert brier_score([True, False], [1.0, 0.0]) == 0.0
    table = calibration_table([True, True, False, False], [0.9, 0.8, 0.2, 0.1], bins=2)
    assert len(table) == 2
    assert table[0]["count"] == 2


def test_geometric_total_and_drawdown() -> None:
    total, max_dd, path = geometric_total([1.0, -2.0, 1.0])
    assert total == pytest.approx((1.01 * 0.98 * 1.01 - 1) * 100)
    assert max_dd < 0
    assert len(path) == 4


def test_quantile() -> None:
    assert quantile([1, 2, 3, 4], 0.5) == 2.5
    assert quantile([], 0.5) == 0.0
