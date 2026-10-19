"""Dead Letter Queue (DLQ) model and class for failed pipeline events."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from sqlalchemy import JSON, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.enums import uuid_str, utcnow
from app.core.logging import get_logger

logger = get_logger(__name__)


def compute_content_hash(title: str, source_id: str, published_date: datetime | str | None) -> str:
    """Compute deterministic SHA256 content hash of normalized title + source + date."""
    from app.pipeline.normalization.normalizer import normalize_text
    norm_title = normalize_text(title or "")
    norm_source = (source_id or "").strip().lower()
    
    date_str = ""
    if isinstance(published_date, datetime):
        date_str = published_date.strftime("%Y-%m-%d")
    elif isinstance(published_date, str) and published_date:
        date_str = published_date[:10]
    else:
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    raw = f"{norm_title}|{norm_source}|{date_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class FailedSignal(Base):
    """Failed ingestion events stored in the Dead Letter Queue."""

    __tablename__ = "failed_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(40), index=True, default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeadLetterQueue:
    """Manages the DLQ for failed pipeline events."""

    @staticmethod
    async def enqueue_failed(session: AsyncSession, event_payload: dict | object, error: Exception | str, source: str = "") -> FailedSignal:
        """Enqueue a failed event into the DLQ table."""
        err_msg = str(error)
        payload_dict = {}
        if isinstance(event_payload, dict):
            payload_dict = event_payload
        elif hasattr(event_payload, "__dict__"):
            payload_dict = {k: v for k, v in event_payload.__dict__.items() if not k.startswith("_")}
        else:
            payload_dict = {"raw": str(event_payload)}

        src = source or payload_dict.get("source_id", "")

        failed_item = FailedSignal(
            raw_payload=payload_dict,
            error_message=err_msg,
            source=src,
            retry_count=0,
            created_at=datetime.now(UTC),
        )
        session.add(failed_item)
        await session.flush()
        logger.error("DLQ enqueue: event from source %s failed: %s (id=%s)", src, err_msg, failed_item.id)
        return failed_item

    @staticmethod
    async def get_failed(session: AsyncSession, limit: int = 50) -> list[FailedSignal]:
        """Get recent failed items for inspection."""
        result = await session.execute(
            select(FailedSignal)
            .order_by(FailedSignal.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def retry_failed(session: AsyncSession, failed_id: str) -> bool:
        """Resubmit a failed item from DLQ back to the pipeline."""
        item = await session.get(FailedSignal, failed_id)
        if not item:
            return False

        item.retry_count = (item.retry_count or 0) + 1
        item.last_retry_at = datetime.now(UTC)
        
        from app.pipeline.collectors.base import RawEvent
        from app.services.pipeline_service import _process_event, PipelineStats, ClusterCandidate, build_default_matcher
        
        raw_data = item.raw_payload
        event = RawEvent(
            source_id=raw_data.get("source_id", item.source),
            external_id=raw_data.get("external_id", "retry-dlq"),
            url=raw_data.get("url", ""),
            title=raw_data.get("title", "Retry Event"),
            description=raw_data.get("description", ""),
            activity=raw_data.get("activity", 1.0),
            activity_metric=raw_data.get("activity_metric"),
            country_code=raw_data.get("country_code"),
            category=raw_data.get("category"),
            hashtags=raw_data.get("hashtags", []),
            thumbnail=raw_data.get("thumbnail"),
            rank=raw_data.get("rank"),
            published_at=datetime.fromisoformat(raw_data["published_at"]) if raw_data.get("published_at") else None,
            observed_at=datetime.fromisoformat(raw_data["observed_at"]) if raw_data.get("observed_at") else None,
            metadata=raw_data.get("metadata", {}),
        )

        stats = PipelineStats()
        recent_events = []
        candidates = []
        matcher = build_default_matcher()
        seen_clusters = set()

        try:
            await _process_event(session, event, candidates, matcher, stats, seen_clusters)
            await session.delete(item)
            await session.commit()
            logger.info("DLQ retry successful for item %s, removed from DLQ", failed_id)
            return True
        except Exception as exc:
            logger.exception("DLQ retry failed for item %s: %r", failed_id, exc)
            item.error_message = f"Retry {item.retry_count} failed: {exc}"
            await session.commit()
            return False

    @staticmethod
    async def purge_old(session: AsyncSession, days: int = 30) -> int:
        """Purge failed items older than specified days."""
        from datetime import timedelta
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await session.execute(
            select(FailedSignal).where(FailedSignal.created_at < cutoff)
        )
        items = result.scalars().all()
        count = len(items)
        for item in items:
            await session.delete(item)
        await session.commit()
        logger.info("Purged %d old DLQ items older than %d days", count, days)
        return count
