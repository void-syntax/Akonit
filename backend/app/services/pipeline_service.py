"""The pipeline orchestrator: COLLECTORS -> NORMALIZE -> DEDUP -> DETECT -> DB.

Every stage is independent; a failure in one source never stops the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Signal, SignalSnapshot, Source, SourceEvent, SourceHealth
from app.models.enums import SignalStatus, SourceStatus
from app.pipeline.collectors.base import FetchContext, FetchResult, RawEvent
from app.pipeline.collectors.http_client import HttpClient
from app.pipeline.collectors.registry import all_adapters, run_strategy_cascade
from app.pipeline.dedup.dedup import ClusterCandidate, find_cluster
from app.pipeline.detection.lifecycle import classify
from app.pipeline.detection.metrics import ActivityPoint, compute_growth_acceleration
from app.pipeline.detection.scoring import strength_components
from app.pipeline.matching.tag_matcher import build_default_matcher
from app.pipeline.normalization.normalizer import (
    canonicalize_url,
    fingerprint,
    simhash,
    slugify,
)
from app.services.retention import expiry_for

logger = get_logger(__name__)

WINDOW_MINUTES = max(settings.snapshot_interval_seconds // 60, 1)


@dataclass
class PipelineStats:
    fetched: int = 0
    events_stored: int = 0
    signals_created: int = 0
    signals_updated: int = 0
    sources_ok: int = 0
    sources_failed: int = 0
    errors: list[str] = field(default_factory=list)


def aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def run_collection_cycle(
    session: AsyncSession,
    *,
    countries: list[str] | None = None,
    limit_per_source: int = 40,
    source_ids: list[str] | None = None,
) -> PipelineStats:
    """One full pass over all enabled sources."""
    stats = PipelineStats()

    client = HttpClient()
    try:
        for adapter in all_adapters():
            if source_ids and adapter.source_id not in source_ids:
                continue
            ctx = FetchContext(
                countries=countries or [], limit=limit_per_source
            )
            try:
                result = await run_strategy_cascade(adapter, ctx, client)
            except Exception as exc:  # isolation guarantee
                logger.exception("collector %s crashed", adapter.source_id)
                stats.errors.append(f"{adapter.source_id}: {exc!r}")
                result = FetchResult(
                    source_id=adapter.source_id,
                    events=[],
                    strategy="none",
                    ok=False,
                    error=repr(exc),
                )

            if result.ok and result.events:
                stats.sources_ok += 1
                stats.fetched += len(result.events)
                try:
                    await _store_result(session, adapter.source_id, result, stats)
                except Exception as exc:
                    logger.exception("storing %s failed", adapter.source_id)
                    stats.errors.append(f"{adapter.source_id} store: {exc!r}")
            else:
                stats.sources_failed += 1
                stats.errors.append(f"{adapter.source_id}: {result.error}")

            try:
                await _update_source_health(session, adapter.source_id, result)
            except Exception as exc:
                logger.warning(
                    "health update failed for %s: %r", adapter.source_id, exc
                )
            await session.commit()
    finally:
        await client.aclose()

    logger.info(
        "collection cycle: %d fetched, %d new signals, %d sources ok",
        stats.fetched,
        stats.signals_created,
        stats.sources_ok,
    )
    return stats


async def _store_result(
    session: AsyncSession,
    source_id: str,
    result: FetchResult,
    stats: PipelineStats,
) -> None:
    """Normalize, dedupe, detect and upsert one source's events."""
    recent_events = (
        (
            await session.execute(
                select(SourceEvent)
                .where(SourceEvent.source_id == source_id)
                .order_by(SourceEvent.observed_at.desc())
                .limit(400)
            )
        )
        .scalars()
        .all()
    )

    candidates: list[ClusterCandidate] = []
    for e in recent_events:
        if not e.cluster_id:
            continue
        try:
            event_hash = int((e.fingerprint or "")[:16], 16)
        except ValueError:
            event_hash = 0
        candidates.append(
            ClusterCandidate(
                cluster_id=e.cluster_id,
                source_id=e.source_id,
                url=e.canonical_url or e.raw_url or "",
                simhash=event_hash,
                observed_at=aware(e.observed_at).timestamp(),
            )
        )

    matcher = build_default_matcher()
    seen_clusters: set[str] = set()

    for event in result.events:
        try:
            # A savepoint keeps one bad event from rolling back the whole batch.
            async with session.begin_nested():
                await _process_event(
                    session, event, candidates, matcher, stats, seen_clusters
                )
            stats.events_stored += 1
        except Exception as exc:  # one bad event must not kill the batch
            logger.warning("event failed (%s): %r", source_id, exc)
            stats.errors.append(f"{source_id} event: {exc}")


async def _process_event(
    session: AsyncSession,
    event: RawEvent,
    candidates: list[ClusterCandidate],
    matcher,
    stats: PipelineStats,
    seen_clusters: set[str],
) -> None:
    canonical_url = canonicalize_url(event.url)
    fp = fingerprint(event.source_id, event.external_id)
    content_hash = simhash(f"{event.title} {event.description}")

    decision = find_cluster(
        event.title,
        event.description,
        event.url,
        event.source_id,
        event.external_id,
        candidates,
    )

    source_event = SourceEvent(
        source_id=event.source_id,
        external_id=event.external_id[:300],
        raw_url=event.url,
        raw_title=event.title[:500],
        raw_activity=event.activity,
        activity_metric=event.activity_metric,
        raw_payload=event.metadata or {},
        canonical_url=canonical_url,
        fingerprint=fp,
        cluster_id=decision.cluster_id,
        country_code=event.country_code,
        rank=event.rank,
        observed_at=aware(event.observed_at),
        normalized=True,
    )
    session.add(source_event)

    signal = (
        (
            await session.execute(
                select(Signal).where(Signal.cluster_id == decision.cluster_id)
            )
        )
        .scalar_one_or_none()
    )

    if signal is None and decision.cluster_id in seen_clusters:
        # Already handled earlier in this same batch.
        return

    if signal is None:
        signal = Signal(
            cluster_id=decision.cluster_id,
            title=event.title[:500],
            slug=slugify(event.title),
            description=(event.description or "")[:2000],
            category=event.category,
            hashtags=event.hashtags or [],
            country_code=event.country_code,
            source_id=event.source_id,
            source_url=event.url,
            thumbnail=event.thumbnail,
            first_seen_at=aware(event.observed_at),
            last_seen_at=aware(event.observed_at),
            current_activity=event.activity,
            previous_activity=0.0,
            activity_metric=event.activity_metric,
            source_metadata=event.metadata or {},
            status=SignalStatus.NEW,
        )
        session.add(signal)
        await session.flush()
        seen_clusters.add(decision.cluster_id)
        session.add(
            SignalSnapshot(
                signal_id=signal.id,
                captured_at=aware(event.observed_at),
                activity=event.activity,
                status=SignalStatus.NEW,
                rank=event.rank,
            )
        )
        stats.signals_created += 1
    else:
        signal.previous_activity = signal.current_activity
        signal.current_activity = event.activity
        signal.last_seen_at = aware(event.observed_at)
        stats.signals_updated += 1

    signal.keywords = _keywords_for(signal, event, matcher)
    await _recompute(session, signal)
    source_event.signal_id = signal.id

    candidates.insert(
        0,
        ClusterCandidate(
            cluster_id=decision.cluster_id,
            source_id=event.source_id,
            url=event.url,
            simhash=content_hash,
            observed_at=aware(event.observed_at).timestamp(),
        ),
    )


def _keywords_for(signal: Signal, event: RawEvent, matcher) -> list[str]:
    """Attach matched tag slugs so radar conditions can filter on them."""
    from app.pipeline.matching.tag_matcher import MatchDocument

    document = MatchDocument(
        title=event.title,
        description=event.description,
        hashtags=event.hashtags or [],
        category=event.category,
        url=event.url,
        source_metadata={"country_code": event.country_code, "source_id": event.source_id},
    )
    try:
        return [m.slug for m in matcher.match(document)]
    except Exception as exc:  # matching must never break ingestion
        logger.debug("tag matching failed for %s: %r", event.external_id, exc)
        return signal.keywords or []


async def _recompute(session: AsyncSession, signal: Signal) -> None:
    """Derive growth / acceleration / status / strength and append a snapshot."""
    history = (
        (
            await session.execute(
                select(SignalSnapshot)
                .where(SignalSnapshot.signal_id == signal.id)
                .order_by(SignalSnapshot.captured_at)
            )
        )
        .scalars()
        .all()
    )

    points = [
        ActivityPoint(captured_at=aware(s.captured_at), activity=s.activity)
        for s in history
    ]
    if not points:
        points = [
            ActivityPoint(
                captured_at=aware(signal.first_seen_at),
                activity=signal.current_activity,
            )
        ]

    metrics = compute_growth_acceleration(
        points, now=datetime.now(UTC), window_minutes=WINDOW_MINUTES
    )
    status, strength = classify(
        metrics,
        previous_status=signal.status,
        cross_source_count=signal.cross_source_count,
        window_minutes=WINDOW_MINUTES,
    )

    signal.growth = round(metrics.growth, 2)
    signal.velocity = round(metrics.velocity, 2)
    # Expiry is set once, at creation, and never moved: a signal that keeps
    # growing for a week is still a week-old signal.
    if signal.expires_at is None:
        signal.expires_at = expiry_for(signal.first_seen_at)
    signal.acceleration = (
        round(metrics.acceleration, 2) if metrics.has_acceleration else 0.0
    )
    signal.status = status
    signal.strength = strength
    signal.last_seen_at = datetime.now(UTC)
    signal.age_minutes = round(metrics.age_minutes, 1)

    session.add(
        SignalSnapshot(
            signal_id=signal.id,
            captured_at=datetime.now(UTC),
            activity=signal.current_activity,
            previous_activity=signal.previous_activity,
            growth=signal.growth,
            acceleration=signal.acceleration,
            strength=signal.strength,
            status=signal.status,
            extra={"components": strength_components(metrics)},
        )
    )


async def _update_source_health(
    session: AsyncSession, source_id: str, result: FetchResult
) -> None:
    source = await session.get(Source, source_id)
    if source is None:
        return

    now = datetime.now(UTC)
    source.last_fetch = now
    source.strategy = result.strategy
    source.rate_limit_remaining = result.rate_limit_remaining
    source.rate_limit_reset_at = result.rate_limit_reset_at

    health = (
        (
            await session.execute(
                select(SourceHealth).where(SourceHealth.source_id == source_id)
            )
        )
        .scalar_one_or_none()
    )
    if health is None:
        health = SourceHealth(source_id=source_id)
        session.add(health)
    health.last_check_at = now

    if result.ok and result.events:
        source.last_success = now
        source.last_error = None
        source.error_count = 0
        source.records_fetched = len(result.events)
        source.total_records += len(result.events)
        if source.status == SourceStatus.OFFLINE:
            source.status = SourceStatus.DEGRADED
        elif source.status != SourceStatus.OPTIONAL_CREDENTIALS:
            source.status = SourceStatus.ACTIVE
        health.consecutive_failures = 0
        health.last_error = None
        if health.status != SourceStatus.OPTIONAL_CREDENTIALS:
            health.status = SourceStatus.ACTIVE
        health.records_last_hour = len(result.events)
        health.strategy = result.strategy
        if health.healthy_since is None:
            health.healthy_since = now
        return

    source.last_error = (result.error or "")[:2000]
    source.error_count = (source.error_count or 0) + 1
    health.consecutive_failures = (health.consecutive_failures or 0) + 1
    health.last_error = (result.error or "")[:2000]

    if source.credentials_required:
        new_status = SourceStatus.OPTIONAL_CREDENTIALS
    elif health.consecutive_failures >= 3:
        new_status = SourceStatus.OFFLINE
    elif health.consecutive_failures >= 1:
        new_status = SourceStatus.DEGRADED
    else:
        new_status = source.status

    source.status = new_status
    health.status = new_status
    health.healthy_since = None


async def refresh_signal_metrics(session: AsyncSession, limit: int = 1000) -> int:
    """Re-derive metrics for existing signals (called by the scheduler)."""
    signals = (
        (
            await session.execute(
                select(Signal)
                .where(Signal.status != SignalStatus.FADING)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    for signal in signals:
        await _recompute(session, signal)
    await session.commit()
    return len(signals)