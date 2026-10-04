"""Retention: fresh signals only, saved signals forever.

The product rule the user asked for, in one place:

  * an unsaved signal disappears SIGNAL_TTL_HOURS after it was first seen
  * a saved signal is never deleted; if the user unsaves it after expiry it
    goes away on the next cleanup run

Everything is deleted in bounded batches so a cleanup never locks the table
and the site stays responsive while it runs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def expiry_for(first_seen_at: datetime | None) -> datetime:
    """Absolute expiry stamp for a freshly detected signal."""
    base = first_seen_at or datetime.now(UTC)
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    return base + timedelta(hours=settings.signal_ttl_hours)


async def _delete_batched(
    session: AsyncSession,
    sql: str,
    params: dict,
    label: str,
) -> int:
    """Run one bounded DELETE and commit only if it removed anything."""
    limit = params.pop("limit", None) or settings.cleanup_max_rows_per_run
    params["limit"] = limit

    result = await session.execute(text(sql), params)
    deleted = result.rowcount or 0

    if deleted:
        await session.commit()
        logger.info("cleanup: deleted %d %s", deleted, label)
    return deleted


async def delete_expired_signals(session: AsyncSession) -> int:
    """Remove expired signals that nobody saved.

    Children (snapshots, radar matches) go with it through ON DELETE CASCADE.
    """
    return await _delete_batched(
        session,
        """
        DELETE FROM signals
        WHERE id IN (
            SELECT s.id
            FROM signals s
            WHERE s.expires_at IS NOT NULL
              AND s.expires_at < :now
              AND NOT EXISTS (
                  SELECT 1 FROM saved_signals ss WHERE ss.signal_id = s.id
              )
            ORDER BY s.expires_at ASC
            LIMIT :limit
        )
        """,
        {"now": datetime.now(UTC)},
        "expired signals",
    )


async def delete_old_source_events(session: AsyncSession) -> int:
    """Trim the raw fetch log.

    Deduplication already happened when the signal was created, so keeping the
    raw payload for months buys nothing. This is the fastest growing table, so
    it gets the shortest life.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=settings.source_event_ttl_hours)
    return await _delete_batched(
        session,
        """
        DELETE FROM source_events
        WHERE id IN (
            SELECT id FROM source_events
            WHERE observed_at < :cutoff
            ORDER BY observed_at ASC
            LIMIT :limit
        )
        """,
        {"cutoff": cutoff},
        "old source events",
    )


async def delete_old_deliveries(session: AsyncSession) -> int:
    """Notification history is useful for a month, then it is noise."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.delivery_ttl_days)
    return await _delete_batched(
        session,
        """
        DELETE FROM notification_deliveries
        WHERE id IN (
            SELECT id FROM notification_deliveries
            WHERE created_at < :cutoff
            LIMIT :limit
        )
        """,
        {"cutoff": cutoff},
        "old deliveries",
    )


async def merge_duplicate_signals(session: AsyncSession) -> int:
    """Collapse signals that share a cluster.

    Clustering should already prevent this, but if it ever missed, two rows for
    the same object would both appear in the feed. The older row wins.
    """
    return await _delete_batched(
        session,
        """
        DELETE FROM signals
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY cluster_id
                           ORDER BY first_seen_at ASC
                       ) AS rn
                FROM signals
                WHERE cluster_id IS NOT NULL
            ) ranked
            WHERE ranked.rn > 1
            LIMIT :limit
        )
        """,
        {},
        "duplicate signals",
    )


async def run_cleanup(session: AsyncSession) -> dict[str, int]:
    """One full maintenance pass. Cheap when there is nothing to do."""
    result = {
        "signals": await delete_expired_signals(session),
        "source_events": await delete_old_source_events(session),
        "deliveries": await delete_old_deliveries(session),
        "duplicates": await merge_duplicate_signals(session),
    }
    if sum(result.values()):
        logger.info("cleanup finished: %s", result)
    return result