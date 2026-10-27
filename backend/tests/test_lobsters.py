"""Lobsters' public API can encode submitters in either common JSON shape."""

import pytest

from app.pipeline.collectors.base import FetchContext
from app.pipeline.collectors.lobsters import LobstersJsonStrategy


class FakeClient:
    async def get_json(self, url: str, retries: int = 1):
        if url.endswith("hottest.json"):
            return [
                "unexpected malformed entry",
                {
                    "short_id": "string-author",
                    "title": "A useful new tool",
                    "url": "https://example.com/tool",
                    "submitter_user": "alice",
                    "score": 4,
                    "comment_count": 2,
                    "tags": ["tools"],
                },
                {
                    "short_id": "object-author",
                    "title": "Another useful tool",
                    "url": "https://example.com/another",
                    "submitter_user": {"username": "bob"},
                    "score": 2,
                    "comment_count": 1,
                },
            ]
        return []


@pytest.mark.asyncio
async def test_lobsters_handles_string_authors_and_malformed_entries():
    events = await LobstersJsonStrategy().fetch(FakeClient(), FetchContext(limit=10))

    assert len(events) == 2
    assert {event.metadata["submitter"] for event in events} == {"alice", "bob"}
