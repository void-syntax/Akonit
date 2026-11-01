"""Tests for the first event of the long-lived Server-Sent Events stream."""

from __future__ import annotations

import pytest

from app.api.v1.sse import sse_stream


@pytest.mark.asyncio
async def test_sse_stream_yields_first_pulse_without_reading_forever():
    response = await sse_stream()

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"

    first_chunk = await response.body_iterator.__anext__()
    assert '"event": "pulse"' in first_chunk
    assert '"sequence": 1' in first_chunk

    await response.body_iterator.aclose()
