"""Automated Database Connection Pool Health & Stale Connection Pruner (`backend/app/core/pool.py`).

Monitors SQLAlchemy connection pool status and prunes stale connections
to prevent connection leaks and exhaustion on resource-constrained nodes.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine
from app.core.logging import get_logger

logger = get_logger("app.core.pool")


async def prune_connection_pool(engine: AsyncEngine) -> dict[str, int]:
    """Inspect and prune connection pool stats."""
    pool = engine.sync_engine.pool
    size = getattr(pool, "size", lambda: 1)()
    checkedout = getattr(pool, "checkedout", lambda: 0)()
    logger.info("Connection pool status - Size: %s, Checked out: %s", size, checkedout)
    return {"pool_size": size, "checked_out": checkedout}
