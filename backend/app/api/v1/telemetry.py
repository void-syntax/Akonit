"""Pipeline Telemetry & Diagnostics API Router (`backend/app/api/v1/telemetry.py`).

Exposes real-time internal runtime metrics for system observability:
- SimHash deduplication stats & duplicate rate
- EventClusterer cross-source grouping metrics
- SQLite database health and page stats
- Memory Guard ring buffer status
"""

from __future__ import annotations

from fastapi import APIRouter
from app.api.deps import SessionDep
from app.core.maintenance import run_sqlite_maintenance
from app.pipeline.simhash import get_deduplicator
from app.pipeline.clustering import get_clusterer
from app.core.memory_guard import get_memory_ring_buffer

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/metrics")
async def get_telemetry_metrics(session: SessionDep) -> dict:
    """Return consolidated telemetry and performance metrics across pipeline subsystems."""
    dedup = get_deduplicator()
    clusterer = get_clusterer()
    memory_guard = get_memory_ring_buffer()
    db_health = await run_sqlite_maintenance(session)

    return {
        "status": "healthy",
        "deduplication": dedup.stats,
        "clustering": {
            "active_clusters": clusterer.size,
        },
        "memory_guard": {
            "current_items": len(memory_guard),
            "max_capacity": memory_guard.max_items,
        },
        "database": db_health,
    }
