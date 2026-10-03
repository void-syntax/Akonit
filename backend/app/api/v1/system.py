"""System endpoints: health, source health summary, manual collection trigger."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core.config import settings
from app.models import Signal, Source, SourceHealth
from app.models.enums import SourceStatus
from app.pipeline.collectors.registry import all_adapters
from sqlalchemy import func, select

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(session: SessionDep):
    signal_count = (
        await session.execute(select(func.count()).select_from(Signal))
    ).scalar_one()
    return {
        "status": "ok",
        "signals": signal_count,
        "registered_sources": len(all_adapters()),
        "environment": settings.app_env,
    }


@router.get("/system/source-health")
async def source_health(session: SessionDep):
    """Honest status per source - never claims 'connected' without data."""
    rows = (
        (
            await session.execute(
                select(Source, SourceHealth)
                .outerjoin(SourceHealth, SourceHealth.source_id == Source.id)
                .order_by(Source.priority)
            )
        )
        .all()
    )

    summary = {status.value: 0 for status in SourceStatus}
    items = []
    for source, health in rows:
        status_value = source.status.value
        summary[status_value] = summary.get(status_value, 0) + 1
        items.append(
            {
                "id": source.id,
                "name": source.name,
                "type": source.type.value,
                "status": status_value,
                "status_reason": source.status_reason,
                "credentials_required": source.credentials_required,
                "cost": source.cost,
                "capabilities": source.capabilities,
                "strategy": source.strategy,
                "last_fetch": source.last_fetch,
                "last_success": source.last_success,
                "last_error": source.last_error,
                "error_count": source.error_count,
                "records_fetched": source.records_fetched,
                "total_records": source.total_records,
                "consecutive_failures": (
                    health.consecutive_failures if health else 0
                ),
                "notes": health.notes if health else None,
            }
        )
    return {"summary": summary, "sources": items}


@router.post("/system/collect")
async def collect_now(session: SessionDep, countries: str | None = None):
    """Manual trigger kept for debugging; the worker runs on its own schedule."""
    from app.services.pipeline_service import run_collection_cycle

    stats = await run_collection_cycle(
        session,
        countries=[c.strip().upper() for c in (countries or "").split(",") if c.strip()],
        limit_per_source=25,
    )
    return {
        "fetched": stats.fetched,
        "signals_created": stats.signals_created,
        "signals_updated": stats.signals_updated,
        "sources_ok": stats.sources_ok,
        "sources_failed": stats.sources_failed,
        "errors": stats.errors[:10],
    }