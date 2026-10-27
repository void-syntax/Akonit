"""Automated Performance Benchmark & Diagnostic Reporter (`backend/app/core/benchmarker.py`).

Measures execution time and memory footprint of core intelligence pipelines
to ensure ongoing performance compliance on resource-constrained nodes.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Coroutine
from app.core.logging import get_logger

logger = get_logger("app.core.benchmarker")


async def benchmark_async_operation(op_name: str, coro_func: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Benchmark execution duration of an asynchronous operation."""
    start_time = time.perf_counter()
    try:
        result = await coro_func(*args, **kwargs)
        duration = time.perf_counter() - start_time
        logger.info("Benchmark [%s] completed in %.4fs", op_name, duration)
        return {"operation": op_name, "duration_seconds": duration, "success": True, "result": result}
    except Exception as exc:
        duration = time.perf_counter() - start_time
        logger.error("Benchmark [%s] failed after %.4fs: %s", op_name, duration, exc)
        return {"operation": op_name, "duration_seconds": duration, "success": False, "error": str(exc)}
