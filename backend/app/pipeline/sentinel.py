"""Asynchronous Circuit Breaker Sentinel & Auto-Recovery Service (`backend/app/pipeline/sentinel.py`).

Continuously monitors degraded collectors, executes automated health resets,
and recovers circuit breakers when external APIs become healthy.
"""

from __future__ import annotations

import asyncio
from app.pipeline.health import get_health_monitor
from app.core.logging import get_logger

logger = get_logger("app.pipeline.sentinel")


class CollectorSentinel:
    """Automated sentinel worker for background circuit breaker recovery."""

    def __init__(self, check_interval: float = 30.0) -> None:
        self.check_interval = check_interval
        self._running = False

    async def sweep(self) -> int:
        """Inspect all circuit breakers and attempt half-open recovery probes."""
        monitor = get_health_monitor()
        report = monitor.health_report()
        tripped = report.get("tripped_circuits", 0)
        
        if tripped > 0:
            logger.warning("Sentinel detected %s tripped circuit breakers. Initiating recovery probe...", tripped)
            for source_id, state in report.get("breakers", {}).items():
                if state == "open":
                    cb = monitor.get_breaker(source_id)
                    # Transition to half-open for testing recovery
                    cb.state = cb.state.__class__.HALF_OPEN  # type: ignore
                    logger.info("Circuit breaker for %s transitioned to HALF_OPEN probe.", source_id)
        return tripped


_sentinel: CollectorSentinel | None = None


def get_sentinel() -> CollectorSentinel:
    global _sentinel
    if _sentinel is None:
        _sentinel = CollectorSentinel()
        logger.info("CollectorSentinel initialized")
    return _sentinel
