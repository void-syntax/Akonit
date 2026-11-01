from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import Signal
from app.pipeline.collectors.base import RawEvent
from app.services.pipeline_service import (
    PipelineStats,
    _process_event,
    aware,
    build_default_matcher,
)


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_repeated_unmeasured_same_source_does_not_refresh_signal(db_session):
    first_seen = datetime.now(UTC) - timedelta(minutes=2)
    first = RawEvent(
        source_id="bluesky_stream",
        external_id="post-1",
        url="https://bsky.app/profile/example/post/1",
        title="A detailed report about a new AI model release and developer tool.",
        activity=0.0,
        activity_metric="live_posts",
        published_at=first_seen,
        observed_at=first_seen,
    )
    candidates = []
    seen_clusters = set()
    stats = PipelineStats()
    matcher = build_default_matcher()

    await _process_event(db_session, first, candidates, matcher, stats, seen_clusters)
    signal = (await db_session.execute(select(Signal))).scalar_one()
    original_last_seen = aware(signal.last_seen_at)

    repeated = RawEvent(
        source_id="bluesky_stream",
        external_id="post-2",
        url=first.url,
        title=first.title,
        activity=0.0,
        activity_metric="live_posts",
        published_at=first_seen,
        observed_at=first_seen + timedelta(minutes=1),
    )
    await _process_event(
        db_session, repeated, candidates, matcher, PipelineStats(), seen_clusters
    )

    assert aware(signal.last_seen_at) == original_last_seen


@pytest.mark.asyncio
async def test_new_independent_source_refreshes_unmeasured_signal(db_session):
    first_seen = datetime.now(UTC) - timedelta(minutes=2)
    title = "A detailed report about a new AI model release and developer tool."
    first = RawEvent(
        source_id="bluesky_stream",
        external_id="post-3",
        url="https://bsky.app/profile/example/post/3",
        title=title,
        activity=0.0,
        activity_metric="live_posts",
        published_at=first_seen,
        observed_at=first_seen,
    )
    candidates = []
    seen_clusters = set()
    await _process_event(
        db_session, first, candidates, build_default_matcher(), PipelineStats(), seen_clusters
    )
    signal = (await db_session.execute(select(Signal))).scalar_one()
    first_timestamp = aware(signal.last_seen_at)

    corroboration = RawEvent(
        source_id="github_trending",
        external_id="repo-1",
        url="https://github.com/example/ai-model-release",
        title=title,
        activity=0.0,
        activity_metric="stars",
        published_at=first_seen,
        observed_at=first_seen + timedelta(minutes=1),
        metadata={"feed_id": "github_trending"},
    )
    await _process_event(
        db_session,
        corroboration,
        candidates,
        build_default_matcher(),
        PipelineStats(),
        seen_clusters,
    )

    assert aware(signal.last_seen_at) > first_timestamp
    assert signal.cross_source_count >= 2
