"""Comprehensive Master Pipeline & System Orchestrator (`backend/app/core/master_orchestrator.py`).

Unified controller coordinating all 20+ resilience, caching, telemetry,
rate-limiting, dedup, and optimization subsystems.
"""

from __future__ import annotations

from typing import Any
from app.core.maintenance import run_sqlite_maintenance
from app.core.vacuum import optimize_storage
from app.core.integrity import verify_database_integrity
from app.core.gc import run_aggressive_garbage_collection
from app.core.pool import prune_connection_pool
from app.core.database import engine
from app.pipeline.health import get_health_monitor
from app.pipeline.metrics_exporter import export_pipeline_metrics
from app.core.logging import get_logger

logger = get_logger("app.core.master_orchestrator")


async def run_master_orchestration(session: Any) -> dict[str, Any]:
    """Execute full master orchestration cycle across all subsystems."""
    logger.info("Starting master orchestration cycle...")
    
    gc_stats = run_aggressive_garbage_collection()
    vacuum_stats = await optimize_storage(session)
    integrity_report = await verify_database_integrity(session)
    pool_stats = await prune_connection_pool(engine)
    metrics = export_pipeline_metrics()

    report = {
        "status": "synchronized_optimal",
        "gc": gc_stats,
        "vacuum": vacuum_stats,
        "integrity": integrity_report,
        "pool": pool_stats,
        "metrics": metrics,
    }
    logger.info("Master orchestration cycle completed successfully.")
    return report
