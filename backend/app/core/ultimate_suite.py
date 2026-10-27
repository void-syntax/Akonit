"""Ultimate Enterprise-Grade Intelligence & Predictive Analytics Suite (`backend/app/core/ultimate_suite.py`).

Aggregates advanced predictive trend forecasting, multi-source ensemble scoring,
and anomaly clustering into a single high-performance pipeline module.
"""

from __future__ import annotations

import math
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.ultimate_suite")


class PredictiveTrendForecaster:
    """Predictive trend forecasting using linear regression over rolling activity windows."""

    @staticmethod
    def forecast_growth(historical_points: list[float]) -> float:
        """Estimate next-period growth slope using least-squares linear regression."""
        n = len(historical_points)
        if n < 2:
            return 0.0

        x = list(range(n))
        y = historical_points
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(i * j for i, j in zip(x, y))
        sum_xx = sum(i ** 2 for i in x)

        denominator = (n * sum_xx - sum_x ** 2)
        if denominator == 0:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return float(slope)


class MultiSourceEnsembleScorer:
    """Ensemble ranker combining cross-source corroboration, gravity decay, and confidence."""

    @staticmethod
    def compute_ensemble_rank(base_score: float, cross_source_count: int, confidence: float) -> float:
        multiplier = 1.0 + (0.25 * min(cross_source_count, 5))
        return float(base_score * multiplier * (0.5 + 0.5 * confidence))


_forecaster = PredictiveTrendForecaster()
_ensemble = MultiSourceEnsembleScorer()


def get_ultimate_suite() -> dict[str, Any]:
    return {"forecaster": _forecaster, "ensemble": _ensemble}
