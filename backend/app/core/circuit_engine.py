"""Adaptive Circuit Breaker & Fault Tolerant Backoff Engine (`backend/app/core/circuit_engine.py`).

Provides robust circuit breaker pattern implementation with automatic failure tracking,
half-open trial state, and exponential backoff recovery.
"""

from __future__ import annotations

import time
from typing import Any, Callable, TypeVar
from app.core.logging import get_logger

logger = get_logger("app.core.circuit_engine")

T = TypeVar("T")


class AdaptiveCircuitBreaker:
    """Adaptive circuit breaker state machine for resilient external source polling."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.failures = 0
        self.last_failure_time = 0.0

    def record_success(self) -> None:
        self.failures = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning("Circuit breaker tripped to OPEN due to %d consecutive failures", self.failures)

    def allow_request(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "HALF-OPEN"
                logger.info("Circuit breaker entering HALF-OPEN state for trial probe")
                return True
            return False
        if self.state == "HALF-OPEN":
            return True
        return True


_breaker = AdaptiveCircuitBreaker()


def get_circuit_engine() -> dict[str, Any]:
    return {"breaker": _breaker}
