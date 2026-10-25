from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.pipeline.collectors import http_client as http_module
from app.pipeline.collectors.http_client import HttpClient, _cache_key, _retry_delay


@pytest.mark.asyncio
async def test_get_reuses_etag_and_treats_304_as_no_change():
    http_module._validators.clear()
    http_module._cached_bodies.clear()
    seen_headers = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers)
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304, request=request)
        return httpx.Response(200, headers={"ETag": '"v1"'}, text="fresh", request=request)

    transport = httpx.MockTransport(handler)
    raw = httpx.AsyncClient(transport=transport)
    client = HttpClient(raw)
    try:
        assert await client.get_text("https://unit.test/feed") == "fresh"
        assert await client.get_text("https://unit.test/feed") == "fresh"
    finally:
        await raw.aclose()

    assert seen_headers[1].get("if-none-match") == '"v1"'


def test_retry_after_supports_seconds_and_http_date():
    response = httpx.Response(429, headers={"Retry-After": "7"})
    assert _retry_delay(response, 1.5, 0) == 7

    retry_at = datetime.now(UTC) + timedelta(seconds=10)
    date_response = httpx.Response(
        503,
        headers={"Retry-After": retry_at.strftime("%a, %d %b %Y %H:%M:%S GMT")},
    )
    assert 0 <= _retry_delay(date_response, 1.5, 0) <= 10


def test_conditional_cache_key_includes_query_parameters():
    assert _cache_key("https://unit.test/search", {"q": "alpha"}) != _cache_key(
        "https://unit.test/search", {"q": "beta"}
    )
