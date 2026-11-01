import asyncio

import pytest

from app.core.config import settings
from app.pipeline.collectors.base import FetchContext
from app.services import pipeline_service


@pytest.mark.asyncio
async def test_collector_timeout_returns_failure_without_waiting_forever(monkeypatch):
    async def never_finishes(*_args):
        await asyncio.Event().wait()

    monkeypatch.setattr(pipeline_service, "run_strategy_cascade", never_finishes)
    monkeypatch.setattr(settings, "source_fetch_timeout_seconds", 0.01)
    result = await pipeline_service._fetch_source_with_deadline(
        type("Adapter", (), {"source_id": "slow-test"})(),
        FetchContext(),
        object(),
    )
    assert result.ok is False
    assert "time budget" in result.error
