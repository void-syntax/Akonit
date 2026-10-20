from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from app.pipeline.collectors import get_adapter, registry_snapshot
from app.pipeline.collectors.adapters.gh_archive import GHArchiveAdapter, GHArchiveEventsStrategy
from app.pipeline.collectors.base import FetchContext


def test_gh_archive_registration():
    adapter = get_adapter("gh_archive")
    assert adapter is not None
    assert isinstance(adapter, GHArchiveAdapter)
    assert adapter.source_id == "gh_archive"
    assert "gh_archive" in adapter.capabilities
    assert "github" in adapter.capabilities
    assert "developer_velocity" in adapter.capabilities

    snapshot = registry_snapshot()
    source_ids = [s["id"] for s in snapshot]
    assert "gh_archive" in source_ids


@pytest.mark.asyncio
async def test_gh_archive_strategy_fetch():
    strategy = GHArchiveEventsStrategy()
    mock_client = AsyncMock()
    mock_client.get_json.return_value = [
        {
            "type": "PushEvent",
            "repo": {"name": "org/ai-agent-framework", "url": "https://api.github.com/repos/org/ai-agent-framework"},
            "actor": {"login": "dev_alice"},
            "payload": {
                "commits": [{"message": "feat: agentic workflow"}, {"message": "fix: streaming bug"}],
            },
            "created_at": "2026-10-20T12:00:00Z",
        },
        {
            "type": "PullRequestEvent",
            "repo": {"name": "org/ai-agent-framework", "url": "https://api.github.com/repos/org/ai-agent-framework"},
            "actor": {"login": "dev_bob"},
            "payload": {},
            "created_at": "2026-10-20T12:05:00Z",
        },
        {
            "type": "WatchEvent",
            "repo": {"name": "org/ai-agent-framework", "url": "https://api.github.com/repos/org/ai-agent-framework"},
            "actor": {"login": "dev_charlie"},
            "payload": {},
            "created_at": "2026-10-20T12:10:00Z",
        }
    ]

    ctx = FetchContext(limit=10)
    events = await strategy.fetch(mock_client, ctx)
    assert len(events) == 1
    event = events[0]
    assert event.source_id == "gh_archive"
    assert event.external_id == "gh_archive:org/ai-agent-framework"
    assert event.title == "org/ai-agent-framework"
    assert event.metadata["commit_count"] == 2
    assert event.metadata["pr_count"] == 1
    assert event.metadata["watch_count"] == 1
    assert event.metadata["unique_contributors"] == 3

    adapter = GHArchiveAdapter()
    acceleration_score = adapter.strategies[0]._calculate_acceleration(event)
    assert acceleration_score > 50.0
