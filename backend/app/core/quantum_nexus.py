"""Small, bounded online helpers for trend smoothing and anomaly detection."""

from __future__ import annotations

import math
from collections import deque
from typing import Any


class RollingIQRAnomalizer:
    """Robust non-parametric anomaly detection using rolling Interquartile Range (IQR)."""

    def __init__(self, window_size: int = 30, multiplier: float = 1.5) -> None:
        if isinstance(window_size, bool) or not isinstance(window_size, int) or window_size < 4:
            raise ValueError("window_size must be an integer of at least 4")
        if not math.isfinite(multiplier) or multiplier < 0:
            raise ValueError("multiplier must be finite and non-negative")
        self.window_size = window_size
        self.multiplier = multiplier
        self.history: deque[float] = deque(maxlen=window_size)

    def is_outlier(self, value: float) -> bool:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        if len(self.history) < 4:
            self.history.append(value)
            return False

        # Judge against previous observations so an extreme new value cannot
        # move its own thresholds and hide itself.
        sorted_vals = sorted(self.history)
        q1 = _percentile(sorted_vals, 0.25)
        q3 = _percentile(sorted_vals, 0.75)
        iqr = q3 - q1

        lower_bound = q1 - (self.multiplier * iqr)
        upper_bound = q3 + (self.multiplier * iqr)

        is_outlier = value < lower_bound or value > upper_bound
        self.history.append(value)
        return is_outlier


class ExponentialSmoothingForecaster:
    """Holt-Winters single exponential smoothing for short-term trend projection."""

    def __init__(self, alpha: float = 0.4) -> None:
        if not math.isfinite(alpha) or not 0 <= alpha <= 1:
            raise ValueError("alpha must be finite and between 0 and 1")
        self.alpha = alpha
        self.level: float | None = None

    def predict_next(self, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        if self.level is None:
            self.level = value
            return value

        self.level = self.alpha * value + (1.0 - self.alpha) * self.level
        return float(self.level)


def _percentile(values: list[float], percentile: float) -> float:
    """Linearly interpolated percentile for an already sorted small window."""
    position = (len(values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


_iqr = RollingIQRAnomalizer()
_es = ExponentialSmoothingForecaster()


def get_quantum_nexus() -> dict[str, Any]:
    return {"iqr": _iqr, "es": _es}
