from __future__ import annotations

import json
from datetime import UTC, datetime
import pytest

from app.core.config import settings
from app.pipeline.collectors.base import FetchContext, SourceUnavailable
from app.pipeline.collectors.x_posts import (
    XRecentSearchStrategy,
    _build_query,
    _read_budget,
)


class FakeXClient:
    def __init__(self, payload):
        self.payload = payload
        self.request_args = None

    async def get_json(self, url, **kwargs):
        self.request_args = (url, kwargs)
        return self.payload


@pytest.mark.asyncio
async def test_x_search_maps_posts_and_enforces_daily_read_budget(monkeypatch, tmp_path):
    state_path = tmp_path / "x-posts-budget-test.json"
    monkeypatch.setattr(settings, "x_api_bearer_token", "test-token")
    monkeypatch.setattr(settings, "x_posts_daily_read_limit", 20)
    from app.pipeline.collectors import x_posts

    monkeypatch.setattr(x_posts, "_state_path", lambda: state_path)
    created_at = "2026-10-28T08:00:00Z"
    client = FakeXClient(
        {
            "data": [
                {
                    "id": "123456",
                    "text": "A new product is trending #launch",
                    "author_id": "author-1",
                    "lang": "en",
                    "created_at": created_at,
                    "public_metrics": {
                        "like_count": 10,
                        "reply_count": 2,
                        "retweet_count": 3,
                        "quote_count": 1,
                    },
                }
            ],
            "meta": {"newest_id": "123456"},
        }
    )

    events = await XRecentSearchStrategy().fetch(
        client, FetchContext(keywords=["new product", "launch"], limit=25)
    )

    assert len(events) == 1
    assert events[0].source_id == "x_posts"
    assert events[0].activity == 16
    assert events[0].published_at == datetime(2026, 10, 28, 8, tzinfo=UTC)
    url, options = client.request_args
    assert url == "https://api.x.com/2/tweets/search/recent"
    assert options["params"]["max_results"] == 10
    assert options["params"]["query"] == '("new product" OR "launch") -is:retweet'
    assert options["headers"]["Authorization"] == "Bearer test-token"
    assert _read_budget(state_path) == (1, "123456")
    assert "test-token" not in state_path.read_text(encoding="utf-8")


def test_corrupt_x_budget_counter_recovers_safely(tmp_path):
    state_path = tmp_path / "budget.json"
    state_path.write_text(
        json.dumps(
            {
                "utc_date": datetime.now(UTC).date().isoformat(),
                "reads": "not-a-number",
                "since_id": 123,
            }
        ),
        encoding="utf-8",
    )

    assert _read_budget(state_path) == (0, "123")


def test_x_query_is_bounded_and_ends_with_retweet_filter():
    query = _build_query([f"topic {index} " + ("x" * 80) for index in range(20)])
    assert len(query) <= 512
    assert query.endswith("-is:retweet")


@pytest.mark.asyncio
async def test_x_search_does_not_call_api_when_daily_budget_cannot_cover_minimum_page(
    monkeypatch, tmp_path
):
    from app.pipeline.collectors import x_posts

    state_path = tmp_path / "x-posts-budget-exhausted-test.json"
    state_path.write_text(
        json.dumps(
            {
                "utc_date": datetime.now(UTC).date().isoformat(),
                "reads": 15,
                "since_id": "123",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(x_posts, "_state_path", lambda: state_path)
    monkeypatch.setattr(settings, "x_api_bearer_token", "test-token")
    monkeypatch.setattr(settings, "x_posts_daily_read_limit", 20)
    client = FakeXClient({})

    with pytest.raises(SourceUnavailable, match="daily X read limit"):
        await XRecentSearchStrategy().fetch(client, FetchContext(limit=10))

    assert client.request_args is None
