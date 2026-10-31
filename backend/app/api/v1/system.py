"""System endpoints: health, source health summary, manual collection trigger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import subprocess
import sys

from fastapi import APIRouter, Query
from sqlalchemy import Text, cast, func, or_, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.models import Signal, Source, SourceHealth, UserProfile
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
        await session.execute(
            select(Source, SourceHealth)
            .outerjoin(SourceHealth, SourceHealth.source_id == Source.id)
            .where(
                or_(
                    Source.status_reason.is_(None),
                    Source.status_reason != "Collector removed; no longer collected.",
                )
            )
            .order_by(Source.priority)
        )
    ).all()

    summary = {status.value: 0 for status in SourceStatus}
    items = []
    adapters = {adapter.source_id: adapter for adapter in all_adapters()}
    for source, health in rows:
        status_value = source.status.value
        summary[status_value] = summary.get(status_value, 0) + 1
        adapter = adapters.get(source.id)
        items.append(
            {
                "id": source.id,
                # Runtime collector definitions are authoritative; the stored
                # source row may predate a rename or capability update.
                "name": adapter.name if adapter else source.name,
                "type": adapter.type.value if adapter else source.type.value,
                "status": status_value,
                "status_reason": source.status_reason,
                "credentials_required": source.credentials_required,
                "cost": source.cost,
                "capabilities": adapter.capabilities if adapter else source.capabilities,
                "strategy": source.strategy,
                "last_fetch": source.last_fetch,
                "last_success": source.last_success,
                "poll_interval_seconds": (
                    adapter.collect_interval_seconds
                    if adapter
                    else source.collect_interval_seconds
                ),
                "last_error": source.last_error,
                "error_count": source.error_count,
                "records_fetched": source.records_fetched,
                "total_records": source.total_records,
                "consecutive_failures": (health.consecutive_failures if health else 0),
                "notes": health.notes if health else None,
            }
        )
    return {"summary": summary, "sources": items}


@router.get("/admin/stats")
async def admin_stats(session: SessionDep):
    """JSON summary of key metrics for the Admin Dashboard."""
    signal_count = (
        await session.execute(select(func.count()).select_from(Signal))
    ).scalar_one()

    # Get DLQ count
    dlq_count = 0
    try:
        from app.pipeline.dlq import DeadLetterQueue

        dlq_items = await DeadLetterQueue.get_failed(session, limit=1000)
        dlq_count = len(dlq_items)
    except Exception:
        pass

    # Import metrics to read sample values/counts
    from app.core.metrics import (
        active_websocket_connections,
        cache_hits_total,
        cache_misses_total,
        dlq_size,
    )

    dlq_size.set(dlq_count)

    return {
        "total_signals": signal_count,
        "active_websocket_connections": active_websocket_connections._value.get(),
        "dlq_size": dlq_count,
        "cache_hits": cache_hits_total._value.get(),
        "cache_misses": cache_misses_total._value.get(),
        "service": "Signal Radar API",
        "status": "healthy",
    }


@router.post("/admin/dlq/{failed_id}/retry")
async def retry_dlq_item(failed_id: str, session: SessionDep):
    """Retry a failed item from the DLQ."""
    from app.pipeline.dlq import DeadLetterQueue

    success = await DeadLetterQueue.retry_failed(session, failed_id)
    if not success:
        return {"status": "error", "message": "Failed item not found or retry failed"}
    return {"status": "ok", "message": f"Successfully retried item {failed_id}"}


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
        ),
        Signal.first_seen_at
        >= datetime.now(UTC) - timedelta(hours=settings.signal_ttl_hours),
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
                statement.order_by(Signal.strength.desc(), Signal.growth.desc()).limit(
                    min(max(limit, 1), 100)
                )
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
    active = by_status["NEW"] + by_status["RISING"] + by_status["BREAKOUT"]

    sources = (
        await session.execute(select(func.count(func.distinct(Signal.source_id))))
    ).scalar_one()
    countries = (
        await session.execute(select(func.count(func.distinct(Signal.country_code))))
    ).scalar_one()

    latest = (
        await session.execute(select(func.max(Signal.first_seen_at)))
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
async def collect_now(
    session: SessionDep, _user: CurrentUser, countries: str | None = None
):
    """Manual trigger kept for debugging; the worker runs on its own schedule."""
    from app.services.pipeline_service import run_collection_cycle

    stats = await run_collection_cycle(
        session,
        countries=[
            c.strip().upper() for c in (countries or "").split(",") if c.strip()
        ],
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


@router.post("/system/pause")
async def pause_worker(_user: CurrentUser):
    from app.core.worker_control import set_worker_paused

    set_worker_paused(True)
    return {"status": "paused"}


@router.post("/system/resume")
async def resume_worker(_user: CurrentUser):
    from app.core.worker_control import set_worker_paused

    set_worker_paused(False)
    return {"status": "running"}


@router.post("/system/start")
async def start_worker(_user: CurrentUser):
    """Start the local worker when its separate process is no longer alive."""
    from app.core.worker_control import acquire_worker_lock, read_worker_status

    # The process lock is authoritative. The heartbeat file can be left stale
    # after Windows kills the worker from stop.bat or during a power event.
    probe = acquire_worker_lock()
    if probe is None:
        return {"status": "running"}
    probe.close()

    snapshot = read_worker_status()
    heartbeat_at = snapshot.get("heartbeat_at")
    if snapshot.get("status") == "running" and heartbeat_at:
        try:
            heartbeat = datetime.fromisoformat(heartbeat_at)
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=UTC)
            if (datetime.now(UTC) - heartbeat.astimezone(UTC)).total_seconds() <= max(
                90, settings.collect_interval_seconds * 3
            ):
                return {"status": "running"}
        except (TypeError, ValueError):
            pass

    backend_root = Path(__file__).resolve().parents[2]
    project_root = backend_root.parent
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    stop_marker = logs_dir / "worker.supervisor.stop"
    stop_marker.unlink(missing_ok=True)
    stdout = (logs_dir / "worker.stdout.log").open("a", encoding="utf-8")
    try:
        kwargs = {
            "cwd": backend_root,
            "stdin": subprocess.DEVNULL,
            "stdout": stdout,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
        }
        if os.name == "nt":
            supervisor = project_root / "worker-supervisor.ps1"
            if supervisor.exists():
                kwargs["cwd"] = project_root
                args = [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(supervisor),
                    "-Python",
                    sys.executable,
                    "-BackendDir",
                    str(backend_root),
                    "-LogDir",
                    str(logs_dir),
                ]
            else:
                args = [sys.executable, "-m", "app.workers.schedule"]
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            )
        else:
            args = [sys.executable, "-m", "app.workers.schedule"]
        subprocess.Popen(args, **kwargs)
    finally:
        stdout.close()
    return {"status": "starting"}


@router.get("/system/worker-status")
async def get_worker_status(session: SessionDep):
    from app.core.worker_control import is_worker_paused, read_worker_status

    paused = is_worker_paused()
    snapshot = read_worker_status()
    heartbeat_at = snapshot.get("heartbeat_at")
    heartbeat_age_seconds = None
    if heartbeat_at:
        try:
            heartbeat = datetime.fromisoformat(heartbeat_at)
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=UTC)
            heartbeat_age_seconds = max(
                0.0, (datetime.now(UTC) - heartbeat.astimezone(UTC)).total_seconds()
            )
        except (TypeError, ValueError):
            heartbeat_age_seconds = None
    fresh_for = max(90, settings.collect_interval_seconds * 3)
    running = (
        snapshot.get("status") == "running"
        and heartbeat_age_seconds is not None
        and heartbeat_age_seconds <= fresh_for
    )
    next_source_check_at = None
    if running and not paused:
        profile = (
            await session.execute(select(UserProfile).limit(1))
        ).scalar_one_or_none()
        weights = (profile.collector_source_weights or {}) if profile else {}
        source_rows = (
            await session.execute(select(Source).where(Source.enabled.is_(True)))
        ).scalars().all()
        adapters = {adapter.source_id: adapter for adapter in all_adapters()}
        now = datetime.now(UTC)
        candidates: list[datetime] = []
        for source in source_rows:
            adapter = adapters.get(source.id)
            try:
                weight = int(weights.get(source.id, 5))
            except (TypeError, ValueError):
                weight = 5
            if adapter is None or weight <= 0:
                continue
            normal_delay = max(
                adapter.collect_interval_seconds, settings.collect_interval_seconds
            )
            if source.error_count:
                retry_delay = min(
                    max(settings.source_cooldown_seconds, 60)
                    * (2 ** min(max((source.error_count or 0) - 1, 0), 5)),
                    1800,
                )
                normal_delay = min(normal_delay, retry_delay)
            effective_delay = normal_delay * 5 / min(max(weight, 1), 10)
            last_fetch = source.last_fetch
            if last_fetch is None:
                candidates.append(now)
            else:
                if last_fetch.tzinfo is None:
                    last_fetch = last_fetch.replace(tzinfo=UTC)
                candidates.append(
                    max(now, last_fetch.astimezone(UTC) + timedelta(seconds=effective_delay))
                )
        if candidates:
            next_source_check_at = min(candidates).isoformat()
    return {
        "running": running,
        "paused": paused,
        "heartbeat_at": heartbeat_at,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "collection_state": snapshot.get("collection_state", "unknown"),
        "last_collection_started_at": snapshot.get("last_collection_started_at"),
        "last_collection_completed_at": snapshot.get("last_collection_completed_at"),
        "last_collection_result": snapshot.get("last_collection_result"),
        "last_collection_error": snapshot.get("last_collection_error"),
        "next_source_check_at": next_source_check_at,
    }
