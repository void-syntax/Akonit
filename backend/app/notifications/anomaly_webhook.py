"""Real-Time Anomaly Alert Webhook Dispatcher (`backend/app/notifications/anomaly_webhook.py`).

Dispatches instant critical webhook alerts when spike detectors
identify rapid breakout trends across monitored sources.
"""

from __future__ import annotations

import httpx
from app.core.logging import get_logger

logger = get_logger("app.notifications.anomaly_webhook")


async def dispatch_anomaly_alert(webhook_url: str, trend_title: str, confidence: float) -> bool:
    """Send real-time webhook notification for detected breakout trends."""
    if not webhook_url:
        return False

    payload = {
        "event": "breakout_trend_detected",
        "title": trend_title,
        "confidence": confidence,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code < 400:
                logger.info("Anomaly webhook alert dispatched successfully for '%s'.", trend_title)
                return True
            else:
                logger.warning("Anomaly webhook returned status %s", response.status_code)
                return False
    except Exception as exc:
        logger.error("Failed to dispatch anomaly webhook: %s", exc)
        return False
