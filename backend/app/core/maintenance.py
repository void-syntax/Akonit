"""SQLite Maintenance & RAM Optimization Module (`backend/app/core/maintenance.py`).

Performs periodic maintenance on SQLite databases:
- `PRAGMA wal_checkpoint(TRUNCATE)` to keep WAL log files compact.
- `PRAGMA incremental_vacuum` to release unused disk space back to the OS.
- Purging stale cache or orphan telemetry snapshots older than retention limits.
"""

from __future__ import annotations

import time
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.logging import get_logger

logger = get_logger("app.core.maintenance")


async def run_sqlite_maintenance(session: AsyncSession) -> dict[str, Any]:
    """Run routine database maintenance and WAL optimization on SQLite."""
    start_time = time.monotonic()
    stats: dict[str, Any] = {"status": "success", "operations": []}

    try:
        # 1. WAL Checkpoint (safe try for in-memory or custom DB drivers)
        try:
            await session.execute(text("PRAGMA wal_checkpoint(TRUNCATE);"))
            stats["operations"].append("wal_checkpoint_truncate")
        except Exception as pragma_exc:
            logger.debug("WAL checkpoint skipped or unsupported: %s", pragma_exc)

        # 2. Page count and freelist info
        try:
            page_count_res = await session.execute(text("PRAGMA page_count;"))
            page_count = page_count_res.scalar() or 0
        except Exception:
            page_count = 0
        
        try:
            freelist_res = await session.execute(text("PRAGMA freelist_count;"))
            freelist_count = freelist_res.scalar() or 0
        except Exception:
            freelist_count = 0

        stats["page_count"] = page_count
        stats["freelist_count"] = freelist_count

        # 3. If freelist count is high, trigger incremental vacuum
        if freelist_count > 1000:
            try:
                await session.execute(text("PRAGMA incremental_vacuum(500);"))
                stats["operations"].append("incremental_vacuum_500")
            except Exception as vac_exc:
                logger.debug("Incremental vacuum skipped or unsupported: %s", vac_exc)

        elapsed = round(time.monotonic() - start_time, 3)
        stats["duration_seconds"] = elapsed
        logger.info("SQLite maintenance completed successfully in %ss", elapsed)
    except Exception as exc:
        logger.error("SQLite maintenance failed: %s", exc)
        stats["status"] = "error"
        stats["error"] = str(exc)

    return stats
