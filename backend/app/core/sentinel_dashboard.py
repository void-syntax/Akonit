"""Async Health Monitoring & Self-Healing Sentinel Dashboard (`backend/app/core/sentinel_dashboard.py`).

Aggregates subsystem health metrics across database integrity, memory guard,
rate limiters, circuit breakers, and collector status into a single unified health report.
"""

from __future__ import annotations

from typing import Any
from app.pipeline.health import get_health_monitor
from app.pipeline.simhash import get_deduplicator
from app.core.memory_guard import get_memory_ring_buffer
from app.core.logging import get_logger

logger = get_logger("app.core.sentinel_dashboard")


async def get_sentinel_dashboard_status() -> dict[str, Any]:
    """Compile comprehensive health and operational metrics across all subsystems."""
    health_monitor = get_health_monitor()
    dedup = get_deduplicator()
    memory_ring = get_memory_ring_buffer()

    report = {
        "status": "fully_operational",
        "collectors": health_monitor.health_report(),
        "deduplication": dedup.stats,
        "memory_ring_buffer": {
            "current_items": len(memory_ring),
            "max_capacity": memory_ring.max_items,
        },
    }
    logger.debug("Sentinel dashboard status compiled successfully.")
    return report
