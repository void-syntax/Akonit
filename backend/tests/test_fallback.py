"""Tests for fallback wrapper module."""

from __future__ import annotations

import asyncio
import pytest
from app.core.fallback import with_fallback


@pytest.mark.asyncio
async def test_with_fallback_success():
    async def primary() -> str:
        return "primary_ok"

    res = await with_fallback(primary(), lambda: "fallback_ok")
    assert res == "primary_ok"


@pytest.mark.asyncio
async def test_with_fallback_triggers():
    async def failing_primary() -> str:
        raise ConnectionError("down")

    res = await with_fallback(failing_primary(), lambda: "fallback_ok")
    assert res == "fallback_ok"
