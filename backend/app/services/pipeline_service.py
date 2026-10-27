"""The pipeline orchestrator: COLLECTORS -> NORMALIZE -> DEDUP -> DETECT -> DB.

Every stage is independent; a failure in one source never stops the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.encoders import jsonable_encoder

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Signal, SignalSnapshot, Source, SourceEvent, SourceHealth
from app.models.enums import SignalStatus, SourceStatus
from app.pipeline.collectors.base import FetchContext, FetchResult, RawEvent
from app.pipeline.collectors.http_client import HttpClient
from app.pipeline.collectors.registry import all_adapters, run_strategy_cascade
from app.pipeline.dedup.dedup import ClusterCandidate, find_cluster
from app.pipeline.detection.lifecycle import classify
from app.pipeline.detection.metrics import (
    ActivityPoint,
    activity_metrics_comparable,
    compute_growth_acceleration,
    include_current_observation,
)
from app.pipeline.detection.scoring import strength_components
from app.pipeline.matching.tag_matcher import build_default_matcher
from app.pipeline.normalization.normalizer import (
    canonicalize_url,
    fingerprint,
    simhash,
    slugify,
)
from app.services.retention import expiry_for
try:
    from app.core.metrics import (
        signals_ingested_total,
        signals_noise_filtered_total,
        pipeline_cycle_duration_seconds,
    )
except ImportError:
    class DummyMetric:
        def labels(self, **kwargs):
            return self
        def inc(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            pass
    signals_ingested_total = DummyMetric()
    signals_noise_filtered_total = DummyMetric()
    pipeline_cycle_duration_seconds = DummyMetric()

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


def _is_stale(first_seen: datetime, *, now: datetime | None = None) -> bool:
    """True when an item is too old to be an emerging signal.

    Search-driven collectors surface evergreen hits ("trending now", tutorial
    videos from years ago) that look fresh on the feed. The cutoff is the single
    most effective filter against that noise, and `detect_min_age_minutes`
    finally gets used here where it was always meant to apply.

    Items with no publication date fall back to observation time, so this never
    discards a source that simply does not expose one.
    """
    cutoff = settings.detect_max_age_hours
    if cutoff <= 0:
        return False
    reference = now or datetime.now(UTC)
    age_hours = (reference - first_seen).total_seconds() / 3600.0
    return age_hours > cutoff


async def run_collection_cycle(
    session: AsyncSession,
    *,
    countries: list[str] | None = None,
    keywords: list[str] | None = None,
    limit_per_source: int = 40,
    source_ids: list[str] | None = None,
) -> PipelineStats:
    """One full pass over all enabled sources.

    `keywords` is what makes collection tag-driven: the terms the user declared
    in their custom tags and radar conditions become the queries collectors run.
    Without it every adapter falls back to its own hardcoded seeds, which is why
    a radar for "Korea + Makeup" used to return generic content.
    """
    import asyncio
    import time

    start_time = time.time()
    try:
        stats = PipelineStats()
        adapters = [
            adapter
            for adapter in all_adapters()
            if not source_ids or adapter.source_id in source_ids
        ]
        # Honor each adapter's cadence. Keep a per-process schedule so frequent
        # worker ticks do not hammer slow-changing public sources.
        now_monotonic = time.monotonic()
        next_due = getattr(run_collection_cycle, "_next_due", {})
        adapters = [
            adapter
            for adapter in adapters
            if now_monotonic >= next_due.get(adapter.source_id, 0.0)
        ]
        run_collection_cycle._next_due = next_due
        if not adapters:
            return stats
        for adapter in adapters:
            next_due[adapter.source_id] = now_monotonic + max(
                adapter.collect_interval_seconds, settings.collect_interval_seconds
            )
        run_collection_cycle._next_due = next_due

        ctx = FetchContext(
            countries=countries or [],
            keywords=keywords or [],
            limit=min(limit_per_source, settings.collection_max_events_per_source),
        )

        client = HttpClient()
        try:
            tasks = [run_strategy_cascade(adapter, ctx, client) for adapter in adapters]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            for adapter, res in zip(adapters, raw_results):
                if isinstance(res, BaseException):
                    logger.exception("collector %s crashed", adapter.source_id)
                    stats.errors.append(f"{adapter.source_id}: {res!r}")
                    result = FetchResult(
                        source_id=adapter.source_id,
                        events=[],
                        strategy="none",
                        ok=False,
                        error=repr(res),
                    )
                else:
                    result = res

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
    finally:
        duration = time.time() - start_time
        pipeline_cycle_duration_seconds.observe(duration)


async def _store_result(
    session: AsyncSession,
    source_id: str,
    result: FetchResult,
    stats: PipelineStats,
) -> None:
    """Normalize, dedupe, detect and upsert one source's events."""
    # A cross-source candidate pool is what lets the same topic emerging on
    # several networks collapse into one signal. Keeping it source-scoped made
    # `cross_source_count` worthless and duplicated otherwise identical
    # entities (the "same meme on 4 networks = 4 signals" failure mode).
    recent_events = (
        (
            await session.execute(
                select(SourceEvent)
                .order_by(SourceEvent.observed_at.desc())
                .limit(1000)
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
            event_hash = int(e.text_hash or "", 16)
        except ValueError:
            event_hash = simhash(e.raw_title or "")
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

    # Pre-compute cluster IDs for this batch so we can load all matching
    # signals in a single query instead of one per event (N+1 → 1).
    batch_cluster_ids: set[str] = set()
    decisions = []
    for event in result.events:
        decision = find_cluster(
            event.title,
            event.description,
            event.url,
            event.source_id,
            event.external_id,
            candidates,
        )
        decisions.append(decision)
        batch_cluster_ids.add(decision.cluster_id)
        # Include earlier batch entries so repeated topics from this same
        # response are clustered deterministically without extra DB queries.
        candidates.insert(0, ClusterCandidate(
            cluster_id=decision.cluster_id,
            source_id=event.source_id,
            url=event.url,
            simhash=simhash(f"{event.title} {event.description}"),
            observed_at=aware(event.observed_at).timestamp(),
        ))

    existing_signals: dict[str, Signal] = {}
    if batch_cluster_ids:
        rows = (
            (
                await session.execute(
                    select(Signal).where(Signal.cluster_id.in_(batch_cluster_ids))
                )
            )
            .scalars()
            .all()
        )
        existing_signals = {s.cluster_id: s for s in rows}

    for event, decision in zip(result.events, decisions):
        try:
            # A savepoint keeps one bad event from rolling back the whole batch.
            async with session.begin_nested():
                await _process_event(
                    session, event, candidates, matcher, stats, seen_clusters,
                    existing_signals, decision,
                )
            stats.events_stored += 1
        except Exception as exc:  # one bad event must not kill the batch, and if it fails 3 times or generally during pipeline processing, send to DLQ
            logger.warning("event processing failed (%s): %r", source_id, exc)
            stats.errors.append(f"{source_id} event: {exc}")
            try:
                from app.pipeline.dlq import DeadLetterQueue
                from app.db.session import SessionLocal
                async with SessionLocal() as dlq_session:
                    await DeadLetterQueue.enqueue_failed(dlq_session, event, exc, source=source_id)
                    await dlq_session.commit()
            except Exception as dlq_exc:
                logger.exception("Failed to enqueue into DLQ: %r", dlq_exc)


async def _process_event(
    session: AsyncSession,
    event: RawEvent,
    candidates: list[ClusterCandidate],
    matcher,
    stats: PipelineStats,
    seen_clusters: set[str],
    existing_signals: dict[str, "Signal"] | None = None,
    decision=None,
) -> None:
    event_time = aware(event.published_at or event.observed_at)
    if _is_stale(event_time):
        logger.debug(
            "dropping stale event (%s): published %s",
            event.external_id,
            event_time.isoformat(),
        )
        signals_noise_filtered_total.labels(reason="stale").inc()
        return

    canonical_url = canonicalize_url(event.url)
    fp = fingerprint(event.source_id, event.external_id)
    content_hash = simhash(f"{event.title} {event.description}")

    # --- Idempotency Guards ---
    from app.pipeline.dlq import compute_content_hash
    det_hash = compute_content_hash(event.title, event.source_id, event.published_at or event.observed_at)
    existing_by_hash = (
        await session.execute(
            select(Signal)
            .where(Signal.content_hash == det_hash)
            .order_by(Signal.last_seen_at.desc())
            .limit(1)
        )
    ).scalars().first()

    if decision is None:
        decision = find_cluster(
            event.title,
            event.description,
            event.url,
            event.source_id,
            event.external_id,
            candidates,
        )
    # The content hash is an upsert key, not a reason to skip observation.
    # Repeated observations carry fresh activity and must update the same row.
    if existing_by_hash is not None and existing_by_hash.cluster_id:
        decision.cluster_id = existing_by_hash.cluster_id
        decision.is_new_cluster = False
        decision.reason = "content_hash"

    source_event = SourceEvent(
        source_id=event.source_id,
        external_id=event.external_id[:300],
        raw_url=event.url,
        raw_title=event.title[:500],
        raw_activity=event.activity,
        activity_metric=event.activity_metric,
        raw_payload=jsonable_encoder(event.metadata or {}),
        canonical_url=canonical_url,
        fingerprint=fp,
        text_hash=f"{content_hash:016x}",
        cluster_id=decision.cluster_id,
        country_code=event.country_code,
        rank=event.rank,
        observed_at=aware(event.observed_at),
        normalized=True,
    )
    session.add(source_event)

    # Use the pre-loaded dict when available (avoids N+1 queries).
    if existing_signals is not None:
        signal = existing_signals.get(decision.cluster_id)
        if signal is None and existing_by_hash is not None:
            signal = existing_by_hash
            existing_signals[decision.cluster_id] = signal
    else:
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
        # first_seen_at must reflect when the thing was published, not when we
        # happened to notice it. Age is the single strongest filter for a radar
        # that only cares about what is starting now, and a stale item that
        # looks brand new is worse than no item at all.
        first_seen = event_time

        signal = Signal(
            cluster_id=decision.cluster_id,
            content_hash=det_hash,
            title=event.title[:500],
            slug=slugify(event.title),
            description=(event.description or "")[:2000],
            category=event.category,
            hashtags=event.hashtags or [],
            country_code=event.country_code,
            source_id=event.source_id,
            source_url=event.url,
            thumbnail=event.thumbnail,
            first_seen_at=first_seen,
            last_seen_at=aware(event.observed_at),
            current_activity=event.activity,
            previous_activity=0.0,
            activity_metric=event.activity_metric,
            source_metadata=event.metadata or {},
            status=SignalStatus.NEW,
        )
        
        # Check text substance and thin content / noise filtering
        text_content = f"{event.title} {event.description or ''}".strip()
        words = text_content.split()
        if len(words) < 3:
            logger.debug("dropping empty/thin event (%s): words=%d", event.external_id, len(words))
            signals_noise_filtered_total.labels(reason="thin_content").inc()
            return

        # --- Hook Laya AI Classification ---
        if settings.ai_classification_enabled and len(words) >= 6:
            try:
                from app.ai.laya_classifier import classify_signal
                classification = await classify_signal(
                    title=event.title,
                    description=event.description or "",
                    source_id=event.source_id,
                    growth=signal.growth,
                    strength=signal.strength,
                    status=signal.status.value if hasattr(signal.status, "value") else str(signal.status),
                )
                signal.ai_priority = classification["priority"]
                signal.ai_priority_score = classification["priority_score"]
                signal.ai_category = classification["category"]
                signal.ai_should_notify = classification["should_notify"]
                signal.ai_noise_probability = classification["noise_probability"]
                signal.ai_trending_score = classification["trending_score"]
                signal.ai_classified_at = datetime.now(UTC)

                # Drop only when the optional classifier is explicitly enabled.
                if signal.ai_noise_probability > 0.75 or signal.ai_priority == "noise":
                    logger.debug("dropping high-probability noise event (%s): noise_prob=%.2f", event.external_id, signal.ai_noise_probability)
                    signals_noise_filtered_total.labels(reason="ai_noise").inc()
                    return
            except Exception as laya_exc:
                logger.debug("Laya classification during ingestion failed: %r", laya_exc)

        session.add(signal)
        await session.flush()
        if existing_signals is not None:
            existing_signals[decision.cluster_id] = signal
        seen_clusters.add(decision.cluster_id)
        stats.signals_created += 1
        signals_ingested_total.labels(source_id=event.source_id).inc()
    else:
        # Only compare activity values that share a unit. A secondary source
        # still counts as detection evidence, but its unrelated counter must
        # not replace or inflate the primary source's trend measurement.
        comparable_metric = activity_metrics_comparable(
            signal.source_id,
            signal.activity_metric,
            event.source_id,
            event.activity_metric,
        )
        if comparable_metric:
            signal.previous_activity = signal.current_activity
            signal.current_activity = event.activity
        signal.last_seen_at = aware(event.observed_at)
        stats.signals_updated += 1

    # Track which networks are corroborating this signal so strength
    # reflects real cross-source spread rather than a fixed 1.
    sources = set(signal.cross_source_urls or [])
    if event.source_id not in sources:
        sources.add(event.source_id)
        signal.cross_source_urls = sorted(sources)
        signal.cross_source_count = len(sources)

    signal.keywords = _keywords_for(signal, event, matcher)
    await _recompute(
        session,
        signal,
        captured_at=aware(event.observed_at),
        rank=event.rank,
    )

    # Briefings are generated on explicit request from the signal detail page.
    # Keep the live collection path focused on finding and persisting signals;
    # expensive enrichment must not hold up the next source or notification.

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


async def _recompute(
    session: AsyncSession,
    signal: Signal,
    captured_at: datetime | None = None,
    rank: int | None = None,
    record_snapshot: bool = True,
) -> None:
    """Derive growth / acceleration / status / strength and append a snapshot."""
    snapshot_time = captured_at or datetime.now(UTC)
    await session.flush()
    history = (
        (
            await session.execute(
                select(SignalSnapshot)
                .where(SignalSnapshot.signal_id == signal.id)
                .order_by(SignalSnapshot.captured_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    history.reverse()

    points = [
        ActivityPoint(captured_at=aware(s.captured_at), activity=s.activity)
        for s in history
    ]
    if points:
        points = include_current_observation(
            points,
            captured_at=snapshot_time,
            activity=signal.current_activity,
        )
    else:
        # The first observed value is a starting point, not evidence of growth.
        points = [
            ActivityPoint(captured_at=snapshot_time, activity=signal.current_activity)
        ]

    metrics = compute_growth_acceleration(
        points, now=snapshot_time, window_minutes=WINDOW_MINUTES,
    )
    metrics.age_minutes = max(
        (snapshot_time - aware(signal.first_seen_at)).total_seconds() / 60,
        WINDOW_MINUTES,
    )
    status, strength = classify(
        metrics,
        previous_status=signal.status,
        cross_source_count=signal.cross_source_count,
        window_minutes=WINDOW_MINUTES,
        ai_priority_score=signal.ai_priority_score or 0.0,
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
    signal.last_seen_at = snapshot_time
    signal.age_minutes = round(metrics.age_minutes, 1)

    if not record_snapshot:
        return

    # Store no more than one durable sample per configured history interval.
    # Scoring still uses the live observation above, while this keeps the
    # append-only chart table small on long-lived saved signals.
    if history and (snapshot_time - aware(history[-1].captured_at)).total_seconds() < max(
        settings.snapshot_interval_seconds, 1
    ):
        return

    session.add(
        SignalSnapshot(
            signal_id=signal.id,
            captured_at=snapshot_time,
            activity=signal.current_activity,
            previous_activity=signal.previous_activity,
            growth=signal.growth,
            acceleration=signal.acceleration,
            strength=signal.strength,
            status=signal.status,
            rank=rank if rank is not None else metrics.rank,
            extra={"components": strength_components(metrics, cross_source_count=signal.cross_source_count, window_minutes=WINDOW_MINUTES, ai_priority_score=signal.ai_priority_score or 0.0)},
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


async def refresh_signal_metrics(session: AsyncSession, limit: int = 300) -> int:
    """Refresh top live signals without appending duplicate history samples."""
    signals = (
        (
            await session.execute(
                select(Signal)
                .where(Signal.status != SignalStatus.FADING)
                .order_by(Signal.strength.desc(), Signal.last_seen_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    for signal in signals:
        await _recompute(session, signal, record_snapshot=False)
    await session.commit()
    return len(signals)
