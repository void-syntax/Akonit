"""Tests for Ultimate Enterprise-Grade Intelligence & Predictive Analytics Suite."""

from __future__ import annotations

import pytest
from app.core.ultimate_suite import PredictiveTrendForecaster, MultiSourceEnsembleScorer, get_ultimate_suite


def test_predictive_trend_forecaster():
    slope = PredictiveTrendForecaster.forecast_growth([10.0, 20.0, 30.0, 40.0])
    assert slope == 10.0

    flat_slope = PredictiveTrendForecaster.forecast_growth([15.0])
    assert flat_slope == 0.0


def test_multi_source_ensemble_scorer():
    rank = MultiSourceEnsembleScorer.compute_ensemble_rank(base_score=10.0, cross_source_count=3, confidence=0.9)
    assert rank > 10.0


def test_ultimate_suite_singleton():
    suite = get_ultimate_suite()
    assert "forecaster" in suite
    assert "ensemble" in suite
