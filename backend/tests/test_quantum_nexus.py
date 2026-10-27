"""Tests for Infinite Multiverse Quantum Nexus & Hyper-Dimensional Matrix."""

from __future__ import annotations

import pytest
from app.core.quantum_nexus import RollingIQRAnomalizer, ExponentialSmoothingForecaster, get_quantum_nexus


def test_rolling_iqr_anomalizer():
    iqr = RollingIQRAnomalizer(window_size=10, multiplier=1.5)
    for v in [10.0, 11.0, 10.5, 12.0, 10.2, 10.8, 11.1, 10.4]:
        assert iqr.is_outlier(v) is False

    # Extreme outlier
    assert iqr.is_outlier(500.0) is True


def test_exponential_smoothing_forecaster():
    es = ExponentialSmoothingForecaster(alpha=0.5)
    p1 = es.predict_next(10.0)
    p2 = es.predict_next(20.0)
    assert p1 == 10.0
    assert p2 == 15.0


def test_quantum_nexus_singleton():
    nexus = get_quantum_nexus()
    assert "iqr" in nexus
    assert "es" in nexus


def test_iqr_uses_previous_values_and_bounds_history():
    detector = RollingIQRAnomalizer(window_size=4)
    for value in (10.0, 10.0, 10.0, 10.0):
        assert detector.is_outlier(value) is False
    assert detector.is_outlier(500.0) is True
    assert len(detector.history) == 4


def test_rejects_invalid_configuration_and_non_finite_values():
    with pytest.raises(ValueError):
        RollingIQRAnomalizer(window_size=3)
    with pytest.raises(ValueError):
        ExponentialSmoothingForecaster(alpha=1.1)
    with pytest.raises(ValueError):
        RollingIQRAnomalizer().is_outlier(float("nan"))
