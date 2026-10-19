"""Tests for Automated Cross-Source Signal Export Service."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import Signal, Source
from app.models.enums import SignalStatus, SourceType
from app.services.export_service import export_intelligence_digest


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
async def test_export_intelligence_digest(db_session: AsyncSession) -> None:
    # Seed a source and signals
    source = Source(
        id="test_source",
        name="Test Source",
        type=SourceType.RSS,
        adapter="rss",
    )
    db_session.add(source)

    signal1 = Signal(
        id="sig-1",
        cluster_id="cluster-1",
        title="Breakout AI Model Released",
        slug="breakout-ai-model-released",
        description="A massive breakout in AI models with 99.9% alpha potential.",
        source_id="test_source",
        source_url="https://example.com/ai-model",
        status=SignalStatus.BREAKOUT,
        strength=85.5,
        growth=120.0,
        ai_priority="critical",
    )
    signal2 = Signal(
        id="sig-2",
        cluster_id="cluster-2",
        title="New Quantum Computing Breakthrough",
        slug="new-quantum-computing-breakthrough",
        description="Quantum qubits stable at room temperature.",
        source_id="test_source",
        source_url="https://example.com/quantum",
        status=SignalStatus.RISING,
        strength=72.0,
        growth=45.0,
        ai_priority="watch",
    )
    db_session.add_all([signal1, signal2])
    await db_session.commit()

    paths = await export_intelligence_digest(db_session, period="daily")
    assert "json_path" in paths
    assert "markdown_path" in paths

    import json
    from pathlib import Path

    json_p = Path(paths["json_path"])
    md_p = Path(paths["markdown_path"])

    assert json_p.exists()
    assert md_p.exists()

    with open(json_p, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["summary"]["total_signals"] >= 2
        assert data["summary"]["breakouts_count"] >= 1
        assert len(data["breakouts"]) >= 1

    md_content = md_p.read_text(encoding="utf-8")
    assert "Akonit Signal Radar" in md_content
    assert "Breakout AI Model Released" in md_content
    assert "New Quantum Computing Breakthrough" in md_content
