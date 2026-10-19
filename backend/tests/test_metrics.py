"""Tests for Prometheus metrics and observability endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.main import app
from app.api.deps import get_session


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
async def test_metrics_endpoint(db_session: AsyncSession):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/metrics")
        assert response.status_code == 200
        body = response.text
        assert "signals_ingested_total" in body
        assert "signals_noise_filtered_total" in body
        assert "laya_classification_duration_seconds" in body
        assert "pipeline_cycle_duration_seconds" in body
        assert "active_websocket_connections" in body
        assert "cache_hits_total" in body
        assert "cache_misses_total" in body
        assert "dlq_size" in body
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_stats_endpoint(db_session: AsyncSession):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/admin/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_signals" in data
        assert "active_websocket_connections" in data
        assert "dlq_size" in data
        assert "cache_hits" in data
        assert "cache_misses" in data
        assert data["status"] == "healthy"
    app.dependency_overrides.clear()
