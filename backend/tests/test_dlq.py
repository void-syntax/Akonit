"""Tests for Dead Letter Queue (DLQ), retry, and idempotency deduplication."""

from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import Signal, SourceEvent
from app.pipeline.dlq import DeadLetterQueue, FailedSignal, compute_content_hash
from app.pipeline.collectors.base import RawEvent
from app.services.pipeline_service import _process_event, PipelineStats, ClusterCandidate, build_default_matcher


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionLocal() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_dlq_enqueue_and_get(db_session: AsyncSession):
    payload = {"source_id": "test_source", "title": "Failed Event", "url": "https://example.com/fail"}
    error = RuntimeError("Test extraction error")

    failed_item = await DeadLetterQueue.enqueue_failed(db_session, payload, error, source="test_source")
    await db_session.commit()

    assert failed_item.id is not None
    assert failed_item.source == "test_source"
    assert "Test extraction error" in failed_item.error_message
    assert failed_item.retry_count == 0

    items = await DeadLetterQueue.get_failed(db_session, limit=10)
    assert len(items) == 1
    assert items[0].id == failed_item.id


@pytest.mark.asyncio
async def test_dlq_purge(db_session: AsyncSession):
    payload = {"title": "Old Failed"}
    item = await DeadLetterQueue.enqueue_failed(db_session, payload, "Old error", source="src")
    item.created_at = datetime.now(UTC) - timedelta(days=40)
    await db_session.commit()

    purged = await DeadLetterQueue.purge_old(db_session, days=30)
    assert purged == 1

    items_after = await DeadLetterQueue.get_failed(db_session)
    assert len(items_after) == 0


@pytest.mark.asyncio
async def test_idempotency_dedup(db_session: AsyncSession):
    now = datetime.now(UTC)
    event1 = RawEvent(
        source_id="github",
        external_id="ext-100",
        url="https://github.com/repo/1",
        title="Unique Testing Breakthrough",
        description="Detailed breakdown of a new architecture.",
        activity=100.0,
        published_at=now,
    )

    stats = PipelineStats()
    candidates = []
    matcher = build_default_matcher()
    seen_clusters = set()

    await _process_event(db_session, event1, candidates, matcher, stats, seen_clusters)
    await db_session.commit()

    assert stats.signals_created == 1

    event2 = RawEvent(
        source_id="github",
        external_id="ext-101",
        url="https://github.com/repo/1-dup",
        title="Unique Testing Breakthrough",
        description="Slightly different description text.",
        activity=150.0,
        published_at=now,
    )

    stats2 = PipelineStats()
    await _process_event(db_session, event2, candidates, matcher, stats2, seen_clusters)
    await db_session.commit()

    signals = (await db_session.execute(Signal.__table__.select())).all()
    assert len(signals) == 1
