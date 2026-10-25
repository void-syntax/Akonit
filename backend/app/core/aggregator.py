"""Memory-Safe Sliding Window Metric Aggregator (`backend/app/core/aggregator.py`).

Aggregates high-frequency pipeline telemetry counts and latencies
with fixed-size ring buffers to maintain strict RAM bounds.
"""

from __future__ import annotations

import time
from collections import deque
from app.core.logging import get_logger

logger = get_logger("app.core.aggregator")


class SlidingWindowAggregator:
    """Fixed-capacity sliding window metric aggregator."""

    def __init__(self, max_samples: int = 1000) -> None:
        self.max_samples = max_samples
        self._samples: deque[tuple[float, float]] = deque(maxlen=max_samples)

    def record(self, value: float) -> None:
        """Record a metric sample with current timestamp."""
        self._samples.append((time.monotonic(), value))

    def average(self) -> float:
        """Calculate average of recorded samples in the sliding window."""
        if not self._samples:
            return 0.0
        return sum(v for _, v in self._samples) / len(self._samples)


_aggregator: SlidingWindowAggregator | None = None


def get_aggregator() -> SlidingWindowAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = SlidingWindowAggregator(max_samples=1000)
        logger.info("SlidingWindowAggregator initialized")
    return _aggregator
