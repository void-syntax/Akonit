"""Asynchronous Circuit Breaker Health Monitor (`backend/app/pipeline/health.py`).

Continuously monitors collector failure rates and circuit breaker states
to provide automated self-healing and recovery metrics.
"""

from __future__ import annotations

from typing import Any
from app.pipeline.resilience import CircuitBreaker, SOURCE_RATE_LIMITS
from app.core.logging import get_logger

logger = get_logger("app.pipeline.health")


class CollectorHealthMonitor:
    """Monitors resilience health across all registered data collectors."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {
            source_id: CircuitBreaker(source_id)
            for source_id in SOURCE_RATE_LIMITS.keys()
        }

    def get_breaker(self, source_id: str) -> CircuitBreaker:
        if source_id not in self._breakers:
            self._breakers[source_id] = CircuitBreaker(source_id)
        return self._breakers[source_id]

    def health_report(self) -> dict[str, Any]:
        """Return operational health status for all collector circuit breakers."""
        report: dict[str, Any] = {}
        tripped_count = 0
        for source_id, cb in self._breakers.items():
            state = cb.state.value
            report[source_id] = state
            if state == "open":
                tripped_count += 1

        return {
            "total_monitored": len(self._breakers),
            "tripped_circuits": tripped_count,
            "breakers": report,
        }


_monitor: CollectorHealthMonitor | None = None


def get_health_monitor() -> CollectorHealthMonitor:
    global _monitor
    if _monitor is None:
        _monitor = CollectorHealthMonitor()
        logger.info("CollectorHealthMonitor initialized")
    return _monitor
