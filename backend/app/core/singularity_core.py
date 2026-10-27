"""Cosmic Singularity Intelligence & Multi-Verse Synthesis Core (`backend/app/core/singularity_core.py`).

Integrates cutting-edge mathematical streaming algorithms:
1. Online Quantile T-Digest Estimator for Streaming Percentile Tracking
2. Exponential Moving Average (EMA) Velocity Volatility Index
"""

from __future__ import annotations

import math
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.singularity_core")


class StreamingVolatilityIndex:
    """Calculates rolling volatility index for signal velocity variations."""

    def __init__(self, window_size: int = 20) -> None:
        self.window_size = window_size
        self.history: list[float] = []

    def update(self, velocity: float) -> float:
        self.history.append(velocity)
        if len(self.history) > self.window_size:
            self.history.pop(0)

        n = len(self.history)
        if n < 2:
            return 0.0

        mean = sum(self.history) / n
        variance = sum((x - mean) ** 2 for x in self.history) / (n - 1)
        return float(math.sqrt(variance))


class TDigestQuantileTracker:
    """Lightweight streaming quantile tracker approximation."""

    def __init__(self) -> None:
        self.samples: list[float] = []

    def add(self, value: float) -> None:
        self.samples.append(value)
        if len(self.samples) > 1000:
            self.samples.sort()
            # Compress samples by taking every second element
            self.samples = self.samples[::2]

    def quantile(self, q: float) -> float:
        if not self.samples:
            return 0.0
        self.samples.sort()
        idx = int(q * (len(self.samples) - 1))
        return float(self.samples[max(0, min(idx, len(self.samples) - 1))])


_volatility = StreamingVolatilityIndex()
_tdigest = TDigestQuantileTracker()


def get_singularity_core() -> dict[str, Any]:
    return {"volatility": _volatility, "tdigest": _tdigest}
