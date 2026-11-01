"""Tests for compression middleware configuration."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.compression import setup_compression


def _build_compression_app() -> FastAPI:
    test_app = FastAPI()

    @test_app.get("/large")
    async def large_response():
        return JSONResponse({"payload": "x" * 1024})

    setup_compression(test_app, minimum_size=128)
    return test_app

@pytest.mark.asyncio
async def test_compression_middleware():
    test_app = _build_compression_app()
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/large", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.json()["payload"] == "x" * 1024
