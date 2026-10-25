"""Automated Database Vacuum & Storage Compactor (`backend/app/core/vacuum.py`).

Performs background storage optimization, index defragmentation,
and frees unused disk space for SQLite/PostgreSQL.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger

logger = get_logger("app.core.vacuum")


async def optimize_storage(session: AsyncSession) -> dict[str, int]:
    """Run database vacuum and optimize storage footprint."""
    try:
        await session.execute(text("VACUUM;"))
        await session.commit()
        logger.info("Database storage successfully vacuumed and optimized.")
        return {"status": 1, "optimized": 1}
    except Exception as exc:
        logger.warning("Storage vacuum skipped or not supported: %s", exc)
        await session.rollback()
        return {"status": 0, "optimized": 0}
