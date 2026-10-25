"""Ultra-fast zero-allocation stream buffer & incremental sliding window aggregator (`backend/app/pipeline/sliding_window.py`).
Computes moving averages, velocity spikes, and anomaly thresholds in O(1) time without memory growth.
"""

from __future__ import annotations

from collections import deque
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.pipeline.sliding_window")


class IncrementalSlidingWindowAggregator:
    """Memory-efficient O(1) sliding window metrics aggregator designed for low-RAM environments."""

    def __init__(self, window_size: int = 100) -> None:
        self.window_size = window_size
        self._values: deque[float] = deque(maxlen=window_size)
        self._sum: float = 0.0

    def add(self, value: float) -> float:
        if len(self._values) == self.window_size:
            self._sum -= self._values[0]
        self._values.append(value)
        self._sum += value
        return self.mean()

    def mean(self) -> float:
        if not self._values:
            return 0.0
        return self._sum / len(self._values)

    def is_spike(self, current_value: float, threshold_multiplier: float = 2.5) -> bool:
        m = self.mean()
        if m == 0.0:
            return current_value > 0
        return current_value >= (m * threshold_multiplier)

    def clear(self) -> None:
        self._values.clear()
        self._sum = 0.0
