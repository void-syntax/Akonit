"""Tests for MasterPipelineOrchestrator."""

from __future__ import annotations

import pytest
from app.core.database import SessionLocal
from app.core.master_orchestrator import run_master_orchestration


@pytest.mark.asyncio
async def test_master_orchestration():
    async with SessionLocal() as session:
        report = await run_master_orchestration(session)
        assert report["status"] == "synchronized_optimal"
        assert "gc" in report
        assert "vacuum" in report
        assert "integrity" in report
        assert "pool" in report
        assert "metrics" in report
