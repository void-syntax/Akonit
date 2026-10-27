"""Tests for Massive Enterprise-Scale Intelligence & Deep Analytics Matrix."""

from __future__ import annotations

import pytest
from app.core.matrix_suite import BayesianConfidenceRating, StreamingMedianAbsoluteDeviation, get_matrix_suite


def test_bayesian_confidence_rating():
    rating = BayesianConfidenceRating(global_mean=3.0, min_votes_threshold=5)
    
    # Low vote count gets shrunk heavily towards global mean (3.0)
    score_low_votes = rating.compute(5.0, vote_count=1)
    # High vote count preserves its high rating
    score_high_votes = rating.compute(5.0, vote_count=100)

    assert score_low_votes < score_high_votes
    assert score_high_votes > 4.5


def test_streaming_median_absolute_deviation():
    vals = [10.0, 12.0, 11.0, 10.5, 100.0]  # 100.0 is an extreme outlier
    z_scores = StreamingMedianAbsoluteDeviation.compute_mad_scores(vals)
    
    assert len(z_scores) == 5
    assert abs(z_scores[-1]) > 2.0  # Outlier has high modified Z-score


def test_matrix_suite_registry():
    registry = get_matrix_suite()
    assert "bayesian" in registry
    assert "mad" in registry
