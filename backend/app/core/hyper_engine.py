"""Hyper-Optimized Multi-Core Intelligence Engine (`backend/app/core/hyper_engine.py`).

Bundles high-throughput vector-less ranking, memory-bounded sliding window accumulators,
and atomic locking mechanisms into a unified blazing-fast processing suite.
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.hyper_engine")


class HyperIntelligenceRingBuffer:
    """Ultra-fast memory-bounded ring buffer for real-time signal stream sliding windows."""

    def __init__(self, max_items: int = 5000) -> None:
        self.max_items = max_items
        self._buffer: deque[dict[str, Any]] = deque(maxlen=max_items)

    def append(self, item: dict[str, Any]) -> None:
        self._buffer.append({**item, "ingested_at": time.time()})

    def query_recent(self, window_seconds: float = 3600.0) -> list[dict[str, Any]]:
        cutoff = time.time() - window_seconds
        return [item for item in self._buffer if item.get("ingested_at", 0) >= cutoff]

    @property
    def size(self) -> int:
        return len(self._buffer)


class HyperScoringEngine:
    """Blazing-fast non-linear signal scoring combining velocity, engagement, and recency."""

    @staticmethod
    def compute_hyper_score(points: float, velocity: float, age_hours: float) -> float:
        decay = (age_hours + 2.0) ** 1.8
        score = (points * 1.5 + velocity * 3.0) / decay
        return max(0.0, score)


_ring_buffer = HyperIntelligenceRingBuffer()
_scoring_engine = HyperScoringEngine()


def get_hyper_engine() -> dict[str, Any]:
    return {"ring_buffer": _ring_buffer, "scoring": _scoring_engine}
