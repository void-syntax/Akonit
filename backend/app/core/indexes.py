"""Database Index Optimization & Query Profiling Module (`backend/app/core/indexes.py`).

Automatically ensures optimal covering indexes exist on SQLite/PostgreSQL
for high-frequency query filters (first_seen_at, strength, status, source_id).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger

logger = get_logger("app.core.indexes")


async def ensure_optimal_indexes(session: AsyncSession) -> None:
    """Create high-performance indexes on critical signal and radar tables if missing."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_signals_strength_seen ON signals(strength DESC, first_seen_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_signals_source_status ON signals(source_id, status);",
        "CREATE INDEX IF NOT EXISTS idx_radarsignals_radar_signal ON radar_signals(radar_id, signal_id);",
    ]
    try:
        for idx_sql in indexes:
            await session.execute(text(idx_sql))
        await session.commit()
        logger.info("Database covering indexes verified and optimized successfully.")
    except Exception as exc:
        logger.debug("Index optimization notice: %s", exc)
        await session.rollback()
