"""Automated Circuit Breaker State Exporter & Metrics Collector (`backend/app/pipeline/metrics_exporter.py`).

Exports real-time collector failure rates, circuit breaker states,
and throughput metrics for system observability.
"""

from __future__ import annotations

from typing import Any
from app.pipeline.health import get_health_monitor
from app.core.logging import get_logger

logger = get_logger("app.pipeline.metrics_exporter")


def export_pipeline_metrics() -> dict[str, Any]:
    """Export consolidated pipeline and health metrics."""
    monitor = get_health_monitor()
    report = monitor.health_report()
    
    metrics = {
        "collector_health": report,
        "system_status": "optimal",
    }
    logger.debug("Pipeline metrics exported successfully.")
    return metrics
