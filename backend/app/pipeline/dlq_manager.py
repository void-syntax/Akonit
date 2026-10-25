"""Asynchronous Event Retry & Dead-Letter Queue (DLQ) Manager (`backend/app/pipeline/dlq.py`).

Автоматически перехватывает сбои при обработке событий и сохраняет их
в памяти с экспоненциальной задержкой и jitter для безопасного повтора.
"""

from __future__ import annotations

import asyncio
import random
from collections import deque
from typing import Any, Callable, Coroutine

from app.core.logging import get_logger

logger = get_logger("app.pipeline.dlq")


class DeadLetterQueue:
    """Memory-bounded Dead-Letter Queue with exponential backoff retry."""

    def __init__(self, maxsize: int = 1000) -> None:
        self.maxsize = maxsize
        self._queue: deque[dict[str, Any]] = deque(maxlen=maxsize)

    def push(self, event: dict[str, Any], error: str) -> None:
        """Push a failed event into the DLQ."""
        item = {
            "event": event,
            "error": error,
            "attempts": event.get("_dlq_attempts", 0) + 1,
            "timestamp": asyncio.get_event_loop().time(),
        }
        item["event"]["_dlq_attempts"] = item["attempts"]
        self._queue.append(item)
        logger.warning("Event pushed to DLQ (attempts=%s, error=%s)", item["attempts"], error)

    async def retry_loop(self, handler: Callable[[dict[str, Any]], Coroutine[Any, Any, bool]], max_attempts: int = 3) -> int:
        """Retry processing queued events with exponential backoff + jitter."""
        retried = 0
        requeue: list[dict[str, Any]] = []

        while self._queue:
            item = self._queue.popleft()
            if item["attempts"] > max_attempts:
                logger.error("Event dropped from DLQ after max attempts exceeded: %s", item["error"])
                continue

            try:
                success = await handler(item["event"])
                if success:
                    retried += 1
                else:
                    # Exponential backoff with jitter
                    backoff = (2 ** item["attempts"]) + random.uniform(0.1, 1.0)
                    await asyncio.sleep(backoff)
                    requeue.append(item)
            except Exception as exc:
                item["error"] = str(exc)
                requeue.append(item)

        for item in requeue:
            self._queue.append(item)

        return retried

    @property
    def size(self) -> int:
        return len(self._queue)

    def clear(self) -> None:
        self._queue.clear()


_dlq: DeadLetterQueue | None = None


def get_dlq() -> DeadLetterQueue:
    global _dlq
    if _dlq is None:
        _dlq = DeadLetterQueue(maxsize=1000)
        logger.info("DeadLetterQueue initialized (maxsize=1000)")
    return _dlq
