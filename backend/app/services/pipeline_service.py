"""The pipeline orchestrator: COLLECTORS -> NORMALIZE -> DEDUP -> DETECT -> DB.

Every stage is independent; a failure in one source never stops the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
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
    mention_burst_score,
)
from app.pipeline.mentions import MentionObservation, summarize_cluster_mentions
from app.pipeline.detection.scoring import strength_components
from app.pipeline.matching.tag_matcher import build_default_matcher
from app.pipeline.normalization.normalizer import (
    canonicalize_url,
    fingerprint,
    normalize_text,
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


def _weighted_source_delay(base_delay: float, weight: int) -> float:
    """Scale the source's normal cadence while keeping weight 1..10 bounded."""
    return base_delay * 5 / min(max(weight, 1), 10)


def _matches_collection_keywords(event: RawEvent, terms: list[str]) -> bool:
    # A profile keyword is an explicit radar query. Requiring it in the title
    # prevents incidental matches in long RSS/search snippets from becoming
    # signals. Tags remain eligible because several APIs expose the topic only
    # as a structured hashtag.
    title = normalize_text(event.title)
    hashtags = normalize_text(" ".join(event.hashtags))
    return any(term in title or term in hashtags for term in terms)


def _snapshot_is_due(
    *,
    record_snapshot: bool,
    record_observation: bool,
    density_count: int,
    history: list[SignalSnapshot],
    captured_at: datetime,
    interval_seconds: int,
) -> bool:
    """Keep a bounded trend history, including count-free source mentions."""
    if not record_snapshot or (not record_observation and density_count <= 0):
        return False
    return not history or (
        captured_at - aware(history[-1].captured_at)
    ).total_seconds() >= max(interval_seconds, 1)


async def _fetch_source_with_deadline(adapter, ctx, client) -> FetchResult:
    """Bound one adapter's full fallback cascade so a hung provider cannot
    hold the entire gather/DB commit hostage for minutes.
    """
    import asyncio

    try:
        return await asyncio.wait_for(
            run_strategy_cascade(adapter, ctx, client),
            timeout=max(settings.source_fetch_timeout_seconds, 1),
        )
    except TimeoutError:
        logger.warning(
            "collector %s exceeded %.1fs budget",
            adapter.source_id,
            settings.source_fetch_timeout_seconds,
        )
        return FetchResult(
            source_id=adapter.source_id,
            events=[],
            strategy="none",
            ok=False,
            error=f"source exceeded {settings.source_fetch_timeout_seconds}s time budget",
        )


async def _fetch_adapter_result(adapter, ctx, client):
    """Attach the source and elapsed time to one isolated fetch task."""
    import time

    started = time.monotonic()
    try:
        result = await _fetch_source_with_deadline(adapter, ctx, client)
    except Exception as exc:
        result = exc
    return adapter, result, time.monotonic() - started


@dataclass
class PipelineStats:
    fetched: int = 0
    events_stored: int = 0
    signals_created: int = 0
    signals_updated: int = 0
    sources_ok: int = 0
    sources_failed: int = 0
    sources_due: int = 0
    errors: list[str] = field(default_factory=list)


def aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    # SQLite drops timezone offsets while storing DateTime values. Normalize
    # non-UTC source timestamps before persistence or e.g. JST items appear 9h
    # in the future and distort freshness/age scoring.
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _effective_event_time(
    published_at: datetime | None, observed_at: datetime | None
) -> datetime:
    """Prevent source clock skew from placing an event in the future."""
    observed = aware(observed_at)
    published = aware(published_at) if published_at is not None else observed
    return min(published, observed)


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
    source_weights: dict[str, int] | None = None,
    required_keywords: list[str] | None = None,
    force: bool = False,
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
    cycle_started = time.monotonic()
    try:
        stats = PipelineStats()
        weights = source_weights or {}
        adapters = [
            adapter
            for adapter in all_adapters()
            if (not source_ids or adapter.source_id in source_ids)
            and weights.get(adapter.source_id, 5) > 0
        ]
        # Honor each adapter's cadence. Keep a per-process schedule so frequent
        # worker ticks do not hammer slow-changing public sources.
        now_monotonic = time.monotonic()
        last_run = getattr(run_collection_cycle, "_last_run", {})
        base_delay = getattr(run_collection_cycle, "_base_delay", {})
        if not force:
            adapters = [
                adapter
                for adapter in adapters
                if now_monotonic
                >= last_run.get(adapter.source_id, 0.0)
                + _weighted_source_delay(
                    base_delay.get(
                        adapter.source_id, adapter.collect_interval_seconds
                    ),
                    weights.get(adapter.source_id, 5),
                )
            ]
        run_collection_cycle._last_run = last_run
        run_collection_cycle._base_delay = base_delay
        if not adapters:
            return stats
        disabled_ids = set(
            (await session.execute(select(Source.id).where(Source.enabled.is_(False))))
            .scalars()
            .all()
        )
        adapters = [
            adapter for adapter in adapters if adapter.source_id not in disabled_ids
        ]
        if not adapters:
            return stats
        stats.sources_due = len(adapters)

        ctx = FetchContext(
            countries=countries or [],
            keywords=keywords or [],
            limit=min(limit_per_source, settings.collection_max_events_per_source),
        )

        client = HttpClient()
        tasks = [
            asyncio.create_task(
                _fetch_adapter_result(adapter, ctx, client),
                name=f"collect:{adapter.source_id}",
            )
            for adapter in adapters
        ]
        fetch_latencies: list[float] = []
        processing_seconds = 0.0
        try:
            # The shared candidate read overlaps network waits. Each source is
            # then processed on completion instead of waiting for the slowest.
            candidates = await _load_recent_cluster_candidates(session)
            search_terms = [
                normalize_text(term)
                for term in (required_keywords or [])
                if term.strip()
            ]
            first_result_latency = None

            for completed in asyncio.as_completed(tasks):
                adapter, res, fetch_elapsed = await completed
                fetch_latencies.append(fetch_elapsed)
                if first_result_latency is None:
                    first_result_latency = time.monotonic() - cycle_started

                if isinstance(res, Exception):
                    logger.error(
                        "collector %s crashed: %r",
                        adapter.source_id,
                        res,
                        exc_info=(type(res), res, res.__traceback__),
                    )
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

                if search_terms and result.ok:
                    result.events = [
                        event
                        for event in result.events
                        if _matches_collection_keywords(event, search_terms)
                    ]

                processing_started = time.monotonic()
                if result.ok:
                    stats.sources_ok += 1
                    stats.fetched += len(result.events)
                    if result.events:
                        try:
                            await _store_result(
                                session,
                                adapter.source_id,
                                result,
                                stats,
                                candidates=candidates,
                            )
                        except Exception as exc:
                            logger.exception("storing %s failed", adapter.source_id)
                            stats.errors.append(f"{adapter.source_id} store: {exc!r}")
                else:
                    stats.sources_failed += 1
                    stats.errors.append(f"{adapter.source_id}: {result.error}")

                last_run[adapter.source_id] = time.monotonic()
                base_delay[adapter.source_id] = _next_source_delay(adapter, result)
                run_collection_cycle._last_run = last_run
                run_collection_cycle._base_delay = base_delay

                try:
                    await _update_source_health(session, adapter.source_id, result)
                except Exception as exc:
                    logger.warning(
                        "health update failed for %s: %r", adapter.source_id, exc
                    )
                await session.commit()
                processing_seconds += time.monotonic() - processing_started

            logger.info(
                "collection timing: first result %.2fs, slowest fetch %.2fs, "
                "source processing %.2fs, cycle %.2fs",
                first_result_latency or 0.0,
                max(fetch_latencies, default=0.0),
                processing_seconds,
                time.monotonic() - cycle_started,
            )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
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


def _next_source_delay(adapter, result) -> float:
    """Retry failures sooner than a healthy source's normal polling interval."""
    normal_interval = max(
        adapter.collect_interval_seconds, settings.collect_interval_seconds
    )
    failures = getattr(run_collection_cycle, "_source_failures", {})
    run_collection_cycle._source_failures = failures

    if result.ok:
        failures.pop(adapter.source_id, None)
        if result.notes in {
            "circuit breaker open",
            "source cooldown after failure",
            "rate limit exceeded",
        }:
            return float(
                min(normal_interval, max(settings.source_cooldown_seconds, 60))
            )
        return float(normal_interval)

    attempts = failures.get(adapter.source_id, 0) + 1
    retry_floor = (
        max(normal_interval, 3600)
        if result.error and "HTTP 429" in result.error
        else max(settings.source_cooldown_seconds, 60)
    )
    failures[adapter.source_id] = attempts
    retry_cap = 3600 if result.error and "HTTP 429" in result.error else 1800
    retry_interval = min(
        retry_floor * (2 ** min(attempts - 1, 5)),
        retry_cap,
    )
    return float(min(normal_interval, retry_interval))


async def _load_recent_cluster_candidates(
    session: AsyncSession,
) -> list[ClusterCandidate]:
    cutoff = datetime.now(UTC) - timedelta(
        minutes=max(settings.detect_dedup_window_minutes, 1) + 5
    )
    item_identity = func.coalesce(
        SourceEvent.canonical_url,
        SourceEvent.external_id,
        SourceEvent.text_hash,
        SourceEvent.id,
    )
    rows = (
        await session.execute(
            select(
                SourceEvent.cluster_id,
                SourceEvent.source_id,
                SourceEvent.external_id,
                SourceEvent.canonical_url,
                SourceEvent.raw_url,
                SourceEvent.text_hash,
                func.min(SourceEvent.observed_at).label("first_observed_at"),
            )
            .where(SourceEvent.observed_at >= cutoff, SourceEvent.cluster_id.is_not(None))
            .group_by(SourceEvent.cluster_id, SourceEvent.source_id, item_identity)
            .order_by(func.min(SourceEvent.observed_at).desc())
            .limit(1000)
        )
    ).all()
    candidates: list[ClusterCandidate] = []
    for event in rows:
        try:
            event_hash = int(event.text_hash or "", 16)
        except ValueError:
            event_hash = simhash(event.canonical_url or event.external_id or "")
        candidates.append(
            ClusterCandidate(
                cluster_id=event.cluster_id,
                source_id=event.source_id,
                url=event.canonical_url or event.raw_url or "",
                simhash=event_hash,
                observed_at=aware(event.first_observed_at).timestamp(),
                title="",
                external_id=event.external_id or "",
            )
        )
    return candidates


async def _store_result(
    session: AsyncSession,
    source_id: str,
    result: FetchResult,
    stats: PipelineStats,
    *,
    candidates: list[ClusterCandidate],
) -> None:
    """Normalize, dedupe, detect and upsert one source's events."""
    # A cross-source candidate pool is what lets the same topic emerging on
    # several networks collapse into one signal. Keeping it source-scoped made
    # `cross_source_count` worthless and duplicated otherwise identical
    # entities (the "same meme on 4 networks = 4 signals" failure mode).
    matcher = build_default_matcher()
    seen_clusters: set[str] = set()

    # Old search hits are common in broad collectors. Drop them before the
    # quadratic similarity scan and database lookups; _process_event retains
    # its guard as a safety net for callers that do not pre-filter batches.
    eligible_events = []
    for event in result.events:
        event_time = _effective_event_time(event.published_at, event.observed_at)
        if _is_stale(event_time):
            signals_noise_filtered_total.labels(reason="stale").inc()
            continue
        eligible_events.append(event)

    # Pre-compute cluster IDs for this batch so we can load all matching
    # signals in a single query instead of one per event (N+1 → 1).
    batch_cluster_ids: set[str] = set()
    decisions = []
    content_fingerprints = []
    for event in eligible_events:
        content_fingerprint = simhash(f"{event.title} {event.description}")
        decision = find_cluster(
            event.title,
            event.description,
            event.url,
            event.source_id,
            event.external_id,
            candidates,
            content_fingerprint=content_fingerprint,
        )
        decisions.append(decision)
        content_fingerprints.append(content_fingerprint)
        batch_cluster_ids.add(decision.cluster_id)
        # Include earlier batch entries so repeated topics from this same
        # response are clustered deterministically without extra DB queries.
        candidates.insert(
            0,
            ClusterCandidate(
                cluster_id=decision.cluster_id,
                source_id=event.source_id,
                url=event.url,
                simhash=content_fingerprint,
                observed_at=aware(event.observed_at).timestamp(),
                title=event.title,
                external_id=event.external_id,
            ),
        )

    # Count distinct items into fixed one-minute bins. SourceEvent stores every
    # poll observation, so counting rows directly inflated density with repeats.
    mention_observations = [
        MentionObservation(
            cluster_id=candidate.cluster_id,
            source_id=candidate.source_id,
            item_id=(
                candidate.canonical_url
                or candidate.external_id
                or f"simhash:{candidate.simhash:016x}"
            ),
            observed_at=candidate.observed_at,
        )
        for candidate in candidates
    ]
    interval_count = max(settings.detect_dedup_window_minutes, 12)
    cluster_activity = summarize_cluster_mentions(
        mention_observations,
        now=datetime.now(UTC).timestamp(),
        interval_count=interval_count,
        baseline_bins=max(interval_count // 2, 1),
    )

    # Upsert checks are batched too; per-event SELECTs were the remaining
    # database round-trip in the hot ingestion loop.
    from app.pipeline.dlq import compute_content_hash

    content_hashes = [
        compute_content_hash(
            event.title,
            event.source_id,
            _effective_event_time(event.published_at, event.observed_at),
        )
        for event in eligible_events
    ]
    event_hashes = set(content_hashes)
    existing_by_hash: dict[str, Signal] = {}
    if event_hashes:
        hash_rows = (
            await session.execute(
                select(Signal)
                .where(Signal.content_hash.in_(event_hashes))
                .order_by(Signal.last_seen_at.desc())
            )
        ).scalars().all()
        for row in hash_rows:
            if row.content_hash:
                existing_by_hash.setdefault(row.content_hash, row)

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

    for event, decision, det_hash, content_fingerprint in zip(
        eligible_events, decisions, content_hashes, content_fingerprints
    ):
        try:
            # A savepoint keeps one bad event from rolling back the whole batch.
            async with session.begin_nested():
                activity = cluster_activity.get(decision.cluster_id)
                await _process_event(
                    session,
                    event,
                    candidates,
                    matcher,
                    stats,
                    seen_clusters,
                    existing_signals,
                    decision,
                    existing_by_hash.get(det_hash),
                    activity.density_count if activity else 1,
                    content_fingerprint,
                    activity.burst_score if activity else 0.0,
                )
            stats.events_stored += 1
        except Exception as exc:  # one bad event must not kill the batch, and if it fails 3 times or generally during pipeline processing, send to DLQ
            logger.warning("event processing failed (%s): %r", source_id, exc)
            stats.errors.append(f"{source_id} event: {exc}")
            try:
                from app.pipeline.dlq import DeadLetterQueue
                from app.db.session import SessionLocal

                async with SessionLocal() as dlq_session:
                    await DeadLetterQueue.enqueue_failed(
                        dlq_session, event, exc, source=source_id
                    )
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
    existing_by_hash: "Signal | None" = None,
    cluster_density: int = 1,
    content_fingerprint: int | None = None,
    burst_score: float = 0.0,
) -> None:
    event_time = _effective_event_time(event.published_at, event.observed_at)
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
    content_hash = (
        content_fingerprint
        if content_fingerprint is not None
        else simhash(f"{event.title} {event.description}")
    )

    # --- Idempotency Guards ---
    from app.pipeline.dlq import compute_content_hash

    det_hash = compute_content_hash(
        event.title, event.source_id, event_time
    )

    if decision is None:
        decision = find_cluster(
            event.title,
            event.description,
            event.url,
            event.source_id,
            event.external_id,
            candidates,
            content_fingerprint=content_hash,
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
            await session.execute(
                select(Signal).where(Signal.cluster_id == decision.cluster_id)
            )
        ).scalar_one_or_none()

    if signal is None and decision.cluster_id in seen_clusters:
        # Already handled earlier in this same batch.
        return

    record_observation = float(event.activity or 0.0) > 0.0
    refresh_freshness = True
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
            # Source metadata is persisted as JSON on both SourceEvent and
            # Signal. Normalize datetimes and other supported values once so
            # a valid collector payload cannot fail the signal insert.
            source_metadata=jsonable_encoder(event.metadata or {}),
            status=SignalStatus.NEW,
        )

        # Check text substance and thin content / noise filtering
        text_content = f"{event.title} {event.description or ''}".strip()
        words = text_content.split()
        if len(words) < 3:
            logger.debug(
                "dropping empty/thin event (%s): words=%d",
                event.external_id,
                len(words),
            )
            signals_noise_filtered_total.labels(reason="thin_content").inc()
            return

        session.add(signal)
        if existing_signals is not None:
            existing_signals[decision.cluster_id] = signal
        seen_clusters.add(decision.cluster_id)
        stats.signals_created += 1
        signals_ingested_total.labels(source_id=event.source_id).inc()
    else:
        if (
            signal.source_id == "google_news_trends"
            and (signal.activity_metric or "").startswith("gnews_")
            and event.activity_metric == "news_mentions"
        ):
            # The old metric was a capped RSS item count, not a trustworthy
            # activity measure. Drop that baseline instead of calling it growth.
            signal.activity_metric = "news_mentions"
            signal.current_activity = 0.0
            signal.previous_activity = 0.0
            signal.growth = 0.0
            signal.velocity = 0.0
            signal.acceleration = 0.0

        # Only compare activity values that share a unit. A secondary source
        # still counts as detection evidence, but its unrelated counter must
        # not replace or inflate the primary source's trend measurement.
        comparable_metric = activity_metrics_comparable(
            signal.source_id,
            signal.activity_metric,
            event.source_id,
            event.activity_metric,
            signal.source_metadata,
            event.metadata,
        )
        record_observation = comparable_metric and float(event.activity or 0.0) > 0.0
        if record_observation:
            signal.previous_activity = signal.current_activity
            signal.current_activity = event.activity
            if signal.source_id == "google_news_trends":
                # Upgrade the old generic name after matching its complete
                # query context; unlike historic mixed-context snapshots, this
                # new series gets a fresh, comparable baseline.
                signal.activity_metric = event.activity_metric
        # A repeated unmeasured observation from an already-counted origin is
        # not fresh evidence. Only measured activity or a genuinely new source
        # should refresh the signal's live-feed timestamp.
        event_origin = _cross_source_origin(event.source_id, event.metadata)
        known_origins = set(signal.cross_source_urls or [])
        if signal.source_id:
            known_origins.add(
                _cross_source_origin(signal.source_id, signal.source_metadata)
            )
        refresh_freshness = record_observation or event_origin not in known_origins
        if refresh_freshness:
            signal.last_seen_at = aware(event.observed_at)
        stats.signals_updated += 1

    # Track which networks are corroborating this signal so strength
    # reflects real cross-source spread rather than a fixed 1.
    sources = set(signal.cross_source_urls or [])
    if signal.source_id:
        sources.add(
            _cross_source_origin(signal.source_id, signal.source_metadata)
        )
    # Migrate the old generic RSS marker when a feed identity is available.
    # A Hacker News RSS mirror is the same origin as Hacker News itself.
    if "rss_news" in sources and event.source_id == "rss_news":
        sources.remove("rss_news")
    sources.add(_cross_source_origin(event.source_id, event.metadata))
    signal.cross_source_urls = sorted(sources)
    # Multiple feeds in the same publishing family are not independent
    # corroboration (for example Bluesky + Mastodon, or RSS + Google News).
    signal.cross_source_count = _cross_source_family_count(sources)
    signal.density_count = max(int(cluster_density), 1)

    # Keep the observation in source_events for audit/history, but avoid
    # repeating snapshot queries, tag matching and strength calculation when
    # an already-counted source repeats an unmeasured item. This is a common
    # hot path for RSS headlines and sampled social streams.
    if not record_observation and not refresh_freshness:
        source_event.signal_id = signal.id
        candidates.insert(
            0,
            ClusterCandidate(
                cluster_id=decision.cluster_id,
                source_id=event.source_id,
                url=event.url,
                simhash=content_hash,
                observed_at=aware(event.observed_at).timestamp(),
                title=event.title,
                external_id=event.external_id,
            ),
        )
        return

    signal.keywords = _keywords_for(signal, event, matcher)
    await _recompute(
        session,
        signal,
        captured_at=aware(event.observed_at),
        rank=event.rank,
        record_observation=record_observation,
        refresh_freshness=refresh_freshness,
        burst_score=burst_score,
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
            title=event.title,
            external_id=event.external_id,
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
        source_metadata={
            "country_code": event.country_code,
            "source_id": event.source_id,
        },
    )
    try:
        return [m.slug for m in matcher.match(document)]
    except Exception as exc:  # matching must never break ingestion
        logger.debug("tag matching failed for %s: %r", event.external_id, exc)
        return signal.keywords or []


def _cross_source_origin(source_id: str, metadata: dict | None = None) -> str:
    """Identify the originating feed so its RSS mirror is not double-counted."""
    if source_id == "gdelt_news":
        domain = str((metadata or {}).get("domain") or "").strip().lower()
        return f"gdelt:{domain}" if domain else source_id
    if source_id != "rss_news":
        return source_id

    feed_id = str((metadata or {}).get("feed_id") or "").strip().lower()
    if "hackernews" in feed_id or feed_id in {"hn", "hacker_news"}:
        return "hackernews"
    return f"rss:{feed_id}" if feed_id else source_id


def _cross_source_family_count(origins: set[str]) -> int:
    """Count distinct source families for corroboration scoring."""
    from app.pipeline.detection.cross_velocity import get_collector_family

    return len({get_collector_family(origin) for origin in origins if origin})


async def _recompute(
    session: AsyncSession,
    signal: Signal,
    captured_at: datetime | None = None,
    rank: int | None = None,
    record_snapshot: bool = True,
    record_observation: bool = True,
    refresh_freshness: bool = True,
    burst_score: float | None = None,
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

    if signal.source_id == "google_news_trends":
        if signal.activity_metric == "news_mentions":
            history = [
                snapshot
                for snapshot in history
                if (snapshot.extra or {}).get("activity_metric") == "news_mentions"
            ]
        elif (signal.activity_metric or "").startswith("gnews_"):
            history = [
                snapshot
                for snapshot in history
                if (snapshot.extra or {}).get("activity_metric") == signal.activity_metric
            ]

    points = [
        ActivityPoint(captured_at=aware(s.captured_at), activity=s.activity)
        for s in history
    ]
    if points and record_observation:
        points = include_current_observation(
            points,
            captured_at=snapshot_time,
            activity=signal.current_activity,
        )
    elif not points and record_observation:
        # The first observed value is a starting point, not evidence of growth.
        points = [
            ActivityPoint(captured_at=snapshot_time, activity=signal.current_activity)
        ]

    metrics = compute_growth_acceleration(
        points,
        now=snapshot_time,
        window_minutes=WINDOW_MINUTES,
    )
    prior_densities = [
        int((snapshot.extra or {}).get("density_count", 0) or 0)
        for snapshot in history
        if (snapshot.extra or {}).get("density_count") is not None
    ]
    # Keep the candidate Poisson score out of production ranking until its
    # event-level holdout has enough examples. The existing robust score stays
    # the ranking input; CUSUM is persisted as a diagnostic for further data.
    metrics.burst_score = mention_burst_score(signal.density_count, prior_densities)
    poisson_diagnostic = (
        min(max(float(burst_score), 0.0), 1.0)
        if burst_score is not None
        else next(
            (
                float((snapshot.extra or {}).get("experimental_poisson_cusum_score"))
                for snapshot in reversed(history)
                if (snapshot.extra or {}).get("experimental_poisson_cusum_score") is not None
            ),
            None,
        )
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
        # Laya may triage a signal, but it cannot boost the metric it is judging.
        ai_priority_score=0.0,
        sources=signal.cross_source_urls or [],
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
    if refresh_freshness:
        signal.last_seen_at = snapshot_time
    signal.age_minutes = round(metrics.age_minutes, 1)

    # Store no more than one durable sample per configured history interval.
    # Scoring still uses the live observation above, while this keeps the
    # append-only chart table small on long-lived saved signals.
    if not _snapshot_is_due(
        record_snapshot=record_snapshot,
        record_observation=record_observation,
        density_count=signal.density_count,
        history=history,
        captured_at=snapshot_time,
        interval_seconds=settings.snapshot_interval_seconds,
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
            extra={
                "activity_metric": signal.activity_metric,
                "density_count": signal.density_count,
                "mention_burst_score": round(metrics.burst_score, 4),
                "experimental_poisson_cusum_score": (
                    round(poisson_diagnostic, 4)
                    if poisson_diagnostic is not None
                    else None
                ),
                "components": strength_components(
                    metrics,
                    cross_source_count=signal.cross_source_count,
                    window_minutes=WINDOW_MINUTES,
                    ai_priority_score=0.0,
                    sources=signal.cross_source_urls or [],
                )
            },
        )
    )


async def normalize_legacy_google_news_metrics(session: AsyncSession) -> int:
    """Remove the old capped-RSS-count baseline from existing news signals."""
    legacy = (
        (
            await session.execute(
                select(Signal).where(
                    Signal.source_id == "google_news_trends",
                    Signal.activity_metric.like("gnews_%"),
                )
            )
        )
        .scalars()
        .all()
    )
    for signal in legacy:
        signal.activity_metric = "news_mentions"
        signal.current_activity = 0.0
        signal.previous_activity = 0.0
        signal.growth = 0.0
        signal.velocity = 0.0
        signal.acceleration = 0.0
        await _recompute(
            session,
            signal,
            record_snapshot=False,
            record_observation=False,
        )
    if legacy:
        await session.commit()
    return len(legacy)


async def normalize_unconfirmed_ai_critical(session: AsyncSession) -> int:
    """Downgrade old AI critical tags that lack engine-measured momentum."""
    candidates = (
        (
            await session.execute(
                select(Signal).where(Signal.ai_priority == "critical")
            )
        )
        .scalars()
        .all()
    )
    downgraded = 0
    for signal in candidates:
        if (
            signal.status in {SignalStatus.RISING, SignalStatus.BREAKOUT}
            and signal.strength >= settings.detect_rising_strength
        ):
            continue
        signal.ai_priority = "watch"
        signal.ai_priority_score = min(signal.ai_priority_score, 0.65)
        signal.ai_should_notify = min(signal.ai_should_notify, 0.3)
        downgraded += 1
    if downgraded:
        await session.commit()
    return downgraded


async def classify_pending_signal_task(session: AsyncSession) -> bool:
    """Classify at most one recent signal outside ingestion's critical path."""
    if not settings.ai_classification_enabled:
        return False
    signal = (
        await session.execute(
            select(Signal)
            .where(
                Signal.ai_classified_at.is_(None),
                Signal.strength >= settings.ai_classification_min_strength,
                Signal.status != SignalStatus.FADING,
            )
            .order_by(Signal.strength.desc(), Signal.first_seen_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if signal is None:
        return False
    try:
        from app.ai.laya_classifier import classify_signal

        result = await classify_signal(
            title=signal.title,
            description=signal.description or "",
            source_id=signal.source_id,
            growth=signal.growth,
            strength=signal.strength,
            status=signal.status.value,
        )
        signal.ai_priority = result["priority"]
        signal.ai_priority_score = result["priority_score"]
        signal.ai_category = result["category"]
        signal.ai_should_notify = result["should_notify"]
        signal.ai_noise_probability = result["noise_probability"]
        signal.ai_trending_score = result["trending_score"]
        signal.ai_model_used = result["model_used"]
        signal.ai_classified_at = datetime.now(UTC)
        await _recompute(session, signal, record_snapshot=False, record_observation=False)
        await session.commit()
        return True
    except Exception as exc:
        logger.warning("background Laya classification failed (%s)", type(exc).__name__)
        await session.rollback()
        return False


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
        await session.execute(
            select(SourceHealth).where(SourceHealth.source_id == source_id)
        )
    ).scalar_one_or_none()
    if health is None:
        health = SourceHealth(source_id=source_id)
        session.add(health)
    health.last_check_at = now

    if result.ok:
        source.last_success = now
        source.last_error = None
        source.error_count = 0
        source.records_fetched = len(result.events)
        source.total_records += len(result.events)
        if source.credentials_required and result.notes and "not configured" in result.notes:
            # The primary adapter may have succeeded through a public fallback,
            # while its optional official API credentials remain unavailable.
            source.status = SourceStatus.OPTIONAL_CREDENTIALS
        elif source.status == SourceStatus.OFFLINE:
            source.status = SourceStatus.DEGRADED
        elif source.status != SourceStatus.OPTIONAL_CREDENTIALS:
            source.status = SourceStatus.ACTIVE
        health.consecutive_failures = 0
        health.last_error = None
        if (
            health.status != SourceStatus.OPTIONAL_CREDENTIALS
            and not (
                source.credentials_required
                and result.notes
                and "not configured" in result.notes
            )
        ):
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
