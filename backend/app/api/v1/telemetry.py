"""Pipeline Telemetry & Diagnostics API Router (`backend/app/api/v1/telemetry.py`).

Exposes real-time internal runtime metrics for system observability:
- SimHash deduplication stats & duplicate rate
- EventClusterer cross-source grouping metrics
- SQLite database health and page stats
- Memory Guard ring buffer status
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select, text
from app.api.deps import SessionDep
from app.pipeline.simhash import get_deduplicator
from app.pipeline.clustering import get_clusterer
from app.core.memory_guard import get_memory_ring_buffer
from app.models import Signal, SourceEvent

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/metrics")
async def get_telemetry_metrics(session: SessionDep) -> dict:
    """Return consolidated telemetry and performance metrics across pipeline subsystems."""
    dedup = get_deduplicator()
    clusterer = get_clusterer()
    memory_guard = get_memory_ring_buffer()
    signals_total = (await session.execute(select(func.count(Signal.id)))).scalar_one()
    recent_sources = (
        await session.execute(
            select(func.count(func.distinct(SourceEvent.source_id))).where(
                SourceEvent.fetched_at >= datetime.now(UTC) - timedelta(hours=24)
            )
        )
    ).scalar_one()
    # Metrics reads must stay cheap and side-effect free. Checkpoint/vacuum is
    # a maintenance operation and should never run just because a dashboard opens.
    db_health: dict[str, Any] = {"status": "unavailable"}
    try:
        page_count = (await session.execute(text("PRAGMA page_count"))).scalar() or 0
        freelist_count = (await session.execute(text("PRAGMA freelist_count"))).scalar() or 0
        db_health = {"status": "healthy", "page_count": page_count, "freelist_count": freelist_count}
    except Exception:
        # Non-SQLite deployments expose the remaining metrics normally.
        pass

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
        "signals": {"total": signals_total},
        "sources": {"active_24h": recent_sources},
    }
