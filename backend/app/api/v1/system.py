"""System endpoints: health, source health summary, manual collection trigger."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import Text, cast, func, or_, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.models import Signal, Source, SourceHealth
from app.models.enums import SourceStatus, SignalStatus
from app.pipeline.collectors.registry import all_adapters
from app.schemas.api import SignalOut

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


@router.get("/discover")
async def discover(
    session: SessionDep,
    limit: int = 40,
    country: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    tag: list[str] | None = Query(default=None),
    min_strength: float | None = None,
):
    """Strongest live signals, independent of any user radar. Public."""
    statement = select(Signal).where(
        Signal.status.in_(
            [SignalStatus.NEW, SignalStatus.RISING, SignalStatus.BREAKOUT]
        )
    )
    # Same semantics as the main feed: lists, so several countries or sources can
    # be picked at once, and everything filters in SQL so the count and the items
    # cannot disagree.
    if country:
        statement = statement.where(
            Signal.country_code.in_([c.upper() for c in country])
        )
    if source:
        statement = statement.where(Signal.source_id.in_(source))
    if min_strength is not None:
        statement = statement.where(Signal.strength >= min_strength)
    if tag:
        needles = [f'"{t.lower()}"' for t in tag if t]
        if needles:
            serialised = cast(Signal.keywords, Text)
            statement = statement.where(
                or_(*[serialised.like(f"%{n}%") for n in needles])
            )

    total = (
        await session.execute(select(func.count()).select_from(statement.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                statement.order_by(
                    Signal.strength.desc(), Signal.growth.desc()
                ).limit(min(max(limit, 1), 100))
            )
        )
        .scalars()
        .unique()
        .all()
    )

    return {
        "total": total,
        "page_count": len(rows),
        "items": [
            {
                field: getattr(signal, field)
                for field in SignalOut.model_fields
                if hasattr(signal, field)
            }
            for signal in rows[:limit]
        ],
    }


@router.get("/stats")
async def public_stats(session: SessionDep):
    """Headline numbers for the landing page — no auth required."""
    rows = (
        await session.execute(
            select(
                Signal.status,
                func.count().label("count"),
            ).group_by(Signal.status)
        )
    ).all()

    by_status = {status.value: 0 for status in SignalStatus}
    for status, count in rows:
        by_status[status.value] = int(count)

    total = sum(by_status.values())
    active = (
        by_status["NEW"] + by_status["RISING"] + by_status["BREAKOUT"]
    )

    sources = (
        await session.execute(
            select(func.count(func.distinct(Signal.source_id)))
        )
    ).scalar_one()
    countries = (
        await session.execute(
            select(func.count(func.distinct(Signal.country_code)))
        )
    ).scalar_one()

    latest = (
        await session.execute(
            select(func.max(Signal.first_seen_at))
        )
    ).scalar_one()

    return {
        "total_signals": total,
        "active_signals": active,
        "breakout": by_status["BREAKOUT"],
        "rising": by_status["RISING"],
        "new": by_status["NEW"],
        "fading": by_status["FADING"],
        "sources": int(sources or 0),
        "countries": int(countries or 0),
        "last_signal_at": latest,
    }


@router.post("/system/collect")
async def collect_now(session: SessionDep, _user: CurrentUser, countries: str | None = None):
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