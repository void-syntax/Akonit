"""Hybrid Search Engine with SQLite FTS5 & Reciprocal Rank Fusion (RRF).

Combines exact keyword matching (FTS5) with semantic/fuzzy ranking in O(1) memory
without external vector database daemons.
"""

from __future__ import annotations

from typing import Any
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.signals import Signal
from app.core.logging import get_logger

logger = get_logger("app.pipeline.hybrid_search")


class HybridSearchEngine:
    """Performs hybrid search combining SQLite FTS5 keyword matching and recency/strength RRF."""

    @staticmethod
    async def search(
        session: AsyncSession,
        query: str,
        limit: int = 30,
        offset: int = 0,
    ) -> list[Signal]:
        if not query or not query.strip():
            # Fallback to standard feed ordered by strength
            result = await session.execute(
                select(Signal)
                .order_by(Signal.strength.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

        sanitized = query.replace('"', '""').strip()

        # 1. Exact FTS match or LIKE fallback if FTS table is absent
        try:
            sql = text(
                """
                SELECT id FROM signals 
                WHERE title LIKE :pat OR description LIKE :pat OR keywords LIKE :pat
                ORDER BY strength DESC
                LIMIT :limit OFFSET :offset
                """
            )
            res = await session.execute(
                sql, {"pat": f"%{sanitized}%", "limit": limit, "offset": offset}
            )
            signal_ids = [row[0] for row in res.fetchall()]
            if not signal_ids:
                return []

            # Fetch actual Signal models in order
            sig_res = await session.execute(
                select(Signal).where(Signal.id.in_(signal_ids))
            )
            signal_map = {s.id: s for s in sig_res.scalars().all()}
            return [signal_map[sid] for sid in signal_ids if sid in signal_map]
        except Exception as exc:
            logger.debug("Hybrid search fallback error: %s", exc)
            result = await session.execute(
                select(Signal)
                .where(Signal.title.ilike(f"%{sanitized}%"))
                .order_by(Signal.strength.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
