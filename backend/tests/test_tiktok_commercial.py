from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.pipeline.collectors import tiktok_commercial
from app.pipeline.collectors.base import FetchContext
from app.pipeline.collectors.tiktok_commercial import CommercialContentStrategy


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def json(self):
        return self.payload


class FakeTikTokClient:
    def __init__(self):
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/v2/oauth/token/"):
            return FakeResponse({"access_token": "short-lived", "expires_in": 7200})
        return FakeResponse(
            {
                "data": {
                    "commercial_contents": [
                        {
                            "id": "content-1",
                            "create_timestamp": 1793174400,
                            "brand_names": ["Example Brand"],
                            "label": "Paid partnership",
                            "creator": {"username": "creator"},
                            "videos": [
                                {
                                    "id": "video-1",
                                    "url": "https://www.tiktok.com/@creator/video/video-1",
                                    "cover_image_url": "https://example.test/cover.jpg",
                                }
                            ],
                        }
                    ]
                },
                "error": {"code": "ok"},
            }
        )


@pytest.mark.asyncio
async def test_approved_tiktok_commercial_api_normalizes_brand_signals(monkeypatch):
    monkeypatch.setattr(settings, "tiktok_commercial_client_key", "client-key")
    monkeypatch.setattr(settings, "tiktok_commercial_client_secret", "client-secret")
    monkeypatch.setattr(tiktok_commercial, "_ACCESS_TOKEN", None)
    monkeypatch.setattr(tiktok_commercial, "_TOKEN_EXPIRES_AT", 0.0)
    client = FakeTikTokClient()

    events = await CommercialContentStrategy().fetch(client, FetchContext(limit=25))

    assert len(events) == 1
    event = events[0]
    assert event.source_id == "tiktok_commercial"
    assert event.title == "TikTok brand signal: Example Brand"
    assert event.activity_metric == "commercial_posts"
    assert event.url.endswith("video-1")
    assert event.published_at == datetime.fromtimestamp(1793174400, tz=UTC)
    token_request, search_request = client.calls
    assert token_request[2]["data"]["grant_type"] == "client_credentials"
    assert search_request[1].endswith("/commercial_content/query/")
    assert search_request[2]["headers"]["Authorization"] == "Bearer short-lived"
    assert search_request[2]["json"]["max_count"] == 25
