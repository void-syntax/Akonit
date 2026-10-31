from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.pipeline.collectors import reddit
from app.pipeline.collectors.reddit import OfficialOAuthStrategy
from app.pipeline.collectors.base import FetchContext


class FakeResponse:
    status_code = 200

    def json(self):
        return {"access_token": "temporary-token", "expires_in": 3600}


class FakeRedditClient:
    def __init__(self):
        self.token_calls = 0
        self.listing_calls = []

    async def request(self, method, url, **kwargs):
        assert method == "POST"
        assert url == "https://www.reddit.com/api/v1/access_token"
        assert kwargs["data"] == {"grant_type": "client_credentials"}
        self.token_calls += 1
        return FakeResponse()

    async def get_json(self, url, **kwargs):
        self.listing_calls.append((url, kwargs))
        subreddit = url.split("/r/", 1)[1].split("/", 1)[0]
        return {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": f"post-{subreddit}",
                            "title": f"A new idea from {subreddit}",
                            "permalink": f"/r/{subreddit}/comments/test/post/",
                            "created_utc": 1793174400,
                            "score": 12,
                            "num_comments": 4,
                            "author": "public-author",
                        }
                    }
                ]
            }
        }


@pytest.mark.asyncio
async def test_reddit_uses_official_oauth_and_rotates_communities(monkeypatch):
    monkeypatch.setattr(settings, "reddit_client_id", "client-id")
    monkeypatch.setattr(settings, "reddit_client_secret", "client-secret")
    monkeypatch.setattr(settings, "reddit_user_agent", "SignalRadarTest/1.0")
    monkeypatch.setattr(reddit, "_REDDIT_ACCESS_TOKEN", None)
    monkeypatch.setattr(reddit, "_REDDIT_TOKEN_EXPIRES_AT", 0.0)
    strategy = OfficialOAuthStrategy()
    client = FakeRedditClient()

    async def collect_twice():
        return (
            await strategy.fetch(client, FetchContext(limit=25)),
            await strategy.fetch(client, FetchContext(limit=25)),
        )

    first, second = await collect_twice()

    assert client.token_calls == 1
    assert len(client.listing_calls) == 10
    assert first and second
    assert all(event.source_id == "reddit" for event in first + second)
    assert all(
        event.activity_metric == "score_plus_comments" for event in first + second
    )
    assert first[0].published_at == datetime.fromtimestamp(1793174400, tz=UTC)
    assert all(
        options["headers"]["Authorization"] == "Bearer temporary-token"
        and options["headers"]["User-Agent"] == "SignalRadarTest/1.0"
        for _, options in client.listing_calls
    )
    assert client.listing_calls[0][0] != client.listing_calls[5][0]
