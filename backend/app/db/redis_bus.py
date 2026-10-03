"""Redis client + pub/sub bus with an in-memory fallback (dev without Redis)."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis: Any | None = None
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_lock = asyncio.Lock()


async def get_redis() -> Any | None:
    global _redis
    if _redis is None and settings.redis_url:
        try:
            from redis.asyncio import from_url

            client = from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
            await client.ping()
            _redis = client
            logger.info("redis connected: %s", settings.redis_url)
        except Exception as exc:  # pragma: no cover - depends on env
            logger.warning("redis unavailable (%s), using in-memory bus", exc)
            _redis = None
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def publish(channel: str, payload: dict[str, Any]) -> None:
    client = await get_redis()
    data = json.dumps(payload, default=str)
    if client is not None:
        try:
            await client.publish(channel, data)
            return
        except Exception as exc:  # pragma: no cover
            logger.warning("redis publish failed (%s), falling back", exc)
    for queue in list(_subscribers[channel]):
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(payload)


async def subscribe(channel: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    async with _lock:
        _subscribers[channel].add(queue)
    return queue


async def unsubscribe(channel: str, queue: asyncio.Queue) -> None:
    async with _lock:
        _subscribers[channel].discard(queue)


# --- helper queues used by the pipeline ---
async def queue_fetch(source_id: str) -> asyncio.Queue:
    return await subscribe(f"collector:{source_id}")


async def queue_fetch_all() -> asyncio.Queue:
    return await subscribe("collector:*")


def broadcast_queues() -> dict[str, set[asyncio.Queue]]:
    return _subscribers