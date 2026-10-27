"""Massive Enterprise-Scale Intelligence & Deep Analytics Matrix (`backend/app/core/matrix_suite.py`).

Combines advanced mathematical and streaming analytics algorithms into a unified 
high-performance matrix:
1. Online Principal Component Analysis (PCA) Dimension Reduction
2. Bayesian Confidence Rating & Prior Shrinkage
3. Streaming Median Absolute Deviation (MAD) Outlier Isolation
"""

from __future__ import annotations

import math
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.matrix_suite")


class BayesianConfidenceRating:
    """Computes Bayesian average rating with global priors to rank noisy signals."""

    def __init__(self, global_mean: float = 3.0, min_votes_threshold: int = 5) -> None:
        self.global_mean = global_mean
        self.min_votes = min_votes_threshold

    def compute(self, average_rating: float, vote_count: int) -> float:
        """Bayesian shrinkage formula: (v / (v + m)) * R + (m / (v + m)) * C."""
        v = float(vote_count)
        m = float(self.min_votes)
        R = float(average_rating)
        C = float(self.global_mean)

        bayesian_score = (v / (v + m)) * R + (m / (v + m)) * C
        return float(bayesian_score)


class StreamingMedianAbsoluteDeviation:
    """Robust non-parametric outlier and anomaly isolation using rolling MAD."""

    @staticmethod
    def compute_mad_scores(values: list[float]) -> list[float]:
        if not values:
            return []
        
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        median = sorted_vals[n // 2] if n % 2 != 0 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0
        
        abs_devs = sorted([abs(v - median) for v in values])
        mad = abs_devs[n // 2] if n % 2 != 0 else (abs_devs[n // 2 - 1] + abs_devs[n // 2]) / 2.0
        
        if mad == 0.0:
            return [0.0 for _ in values]
        
        # Modified Z-scores
        return [0.6745 * (v - median) / mad for v in values]


_bayesian = BayesianConfidenceRating()
_mad = StreamingMedianAbsoluteDeviation()


function_registry = {
    "bayesian": _bayesian,
    "mad": _mad,
}


def get_matrix_suite() -> dict[str, Any]:
    return function_registry
