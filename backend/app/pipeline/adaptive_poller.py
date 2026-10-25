"""Asynchronous Smart Backoff & Jitter Adaptive Poller (`backend/app/pipeline/adaptive_poller.py`).

Dynamically adjusts collection intervals for each source based on historical
activity velocity and rate limit feedback to maximize signal freshness
while preserving system resources.
"""

from __future__ import annotations

import asyncio
import random
from app.core.logging import get_logger

logger = get_logger("app.pipeline.adaptive_poller")


class AdaptivePollingController:
    """Dynamic polling interval controller with velocity feedback."""

    def __init__(self, base_interval: float = 60.0, min_interval: float = 10.0, max_interval: float = 600.0) -> None:
        self.base_interval = base_interval
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._intervals: dict[str, float] = {}

    def get_interval(self, source_id: str) -> float:
        """Get current adaptive polling interval for a source."""
        return self._intervals.get(source_id, self.base_interval)

    def adapt(self, source_id: str, high_velocity: bool) -> float:
        """Adjust interval based on whether recent polls yielded high signal velocity."""
        current = self.get_interval(source_id)
        if high_velocity:
            # Speed up collection if high activity detected
            new_val = max(self.min_interval, current * 0.75)
        else:
            # Slow down collection if low activity to save bandwidth/CPU
            new_val = min(self.max_interval, current * 1.25)
        
        # Add jitter
        jittered = new_val + random.uniform(-1.0, 1.0)
        self._intervals[source_id] = jittered
        logger.debug("Adapted polling interval for %s: %.2fs (high_velocity=%s)", source_id, jittered, high_velocity)
        return jittered


_controller: AdaptivePollingController | None = None


def get_adaptive_poller() -> AdaptivePollingController:
    global _controller
    if _controller is None:
        _controller = AdaptivePollingController()
        logger.info("AdaptivePollingController initialized")
    return _controller
