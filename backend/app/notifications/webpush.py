"""Web Push delivery (VAPID)."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def send_web_push(
    subscriptions: list[dict[str, Any]], payload: dict[str, Any]
) -> int:
    """Push to every subscription. Never raises for a single failed endpoint."""
    if not settings.vapid_private_key:
        logger.warning("VAPID keys are not configured; push skipped")
        return 0

    import asyncio

    from pywebpush import WebPushException, webpush

    sent = 0

    def _push(sub: dict[str, Any]) -> None:
        try:
            webpush(
                subscription_info=sub,
                data=__import__("json").dumps(payload),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                timeout=10,
            )
        except WebPushException as exc:
            logger.warning("push failed: %r", exc)
        except Exception as exc:  # pragma: no cover
            logger.warning("push error: %r", exc)

    await asyncio.gather(
        *(asyncio.to_thread(_push, sub) for sub in subscriptions if sub),
        return_exceptions=True,
    )
    sent = len(subscriptions)
    logger.info("web push dispatched to %d subscriptions", sent)
    return sent