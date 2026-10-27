"""Infinite Dimensional Quantum-Core & Hyper-Stream Intelligence (`backend/app/core/infinite_core.py`).

Integrates cutting-edge mathematical streaming analytics:
1. Count-Min Sketch Frequency Estimator for High-Throughput Stream Deduplication
2. Hyperbolic Decay Time-Weighting Function for Long-Tail Signal Prioritization
"""

from __future__ import annotations

import math
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.infinite_core")


class CountMinSketch:
    """Memory-efficient probabilistic frequency estimator for streaming events."""

    def __init__(self, width: int = 1000, depth: int = 5) -> None:
        self.width = width
        self.depth = depth
        self.table = [[0] * width for _ in range(depth)]

    def _hash(self, item: str, seed: int) -> int:
        return abs(hash(f"{seed}_{item}")) % self.width

    def add(self, item: str) -> None:
        for i in range(self.depth):
            idx = self._hash(item, i)
            self.table[i][idx] += 1

    def estimate(self, item: str) -> int:
        min_val = float('inf')
        for i in range(self.depth):
            idx = self._hash(item, i)
            min_val = min(min_val, self.table[i][idx])
        return int(min_val) if min_val != float('inf') else 0


class HyperbolicDecayScorer:
    """Hyperbolic time-decay weighting for long-tail trending signals."""

    @staticmethod
    def compute_weight(age_hours: float, scaling_factor: float = 24.0) -> float:
        if age_hours < 0:
            age_hours = 0.0
        return 1.0 / (1.0 + (age_hours / scaling_factor))


_cms = CountMinSketch()
_hds = HyperbolicDecayScorer()


def get_infinite_core() -> dict[str, Any]:
    return {"cms": _cms, "hds": _hds}
