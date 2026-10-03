"""Notification dispatcher.

Separate from the signal engine by design: the engine decides WHAT happened,
the dispatcher decides WHEN and WHERE to deliver it. Frequency modes are
OFF / INSTANT / EVERY_15_MIN / HOURLY / DAILY_DIGEST.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models import (
    NotificationDelivery,
    NotificationPreference,
    Radar,
    RadarSignal,
    Signal,
    UserProfile,
)
from app.models.enums import (
    DeliveryStatus,
    NotificationChannel,
    NotificationFrequency,
    SignalStatus,
)
from app.notifications.formatter import format_signal_alert, format_web_push
from app.notifications.telegram import TelegramClient
from app.notifications.webpush import send_web_push

logger = get_logger(__name__)

FREQUENCY_DELAY = {
    NotificationFrequency.INSTANT: timedelta(0),
    NotificationFrequency.EVERY_15_MIN: timedelta(minutes=15),
    NotificationFrequency.HOURLY: timedelta(hours=1),
    NotificationFrequency.DAILY_DIGEST: timedelta(days=1),
}


async def notify_matches(
    session: AsyncSession,
    *,
    signal_ids: list[str] | None = None,
    radar_id: str | None = None,
    now: datetime | None = None,
) -> int:
    """Queue deliveries for every radar match that is due. Returns the count."""
    now = now or datetime.now(UTC)
    statement = select(RadarSignal).where(RadarSignal.notified_at.is_(None))
    if radar_id:
        statement = statement.where(RadarSignal.radar_id == radar_id)
    if signal_ids:
        statement = statement.where(RadarSignal.signal_id.in_(signal_ids))

    matches = (await session.execute(statement)).scalars().all()
    queued = 0

    for match in matches:
        if match.is_dismissed:
            continue
        signal = await session.get(Signal, match.signal_id)
        radar = await session.get(Radar, match.radar_id)
        if signal is None or radar is None:
            continue
        if signal.status == SignalStatus.FADING or not radar.is_active:
            continue

        delay = FREQUENCY_DELAY.get(radar.notification_frequency, timedelta(0))
        last = radar.last_notified_at or EPOCH
        if last + delay > now:
            continue

        for channel_name in radar.notification_channels or [
            NotificationChannel.WEB_PUSH.value
        ]:
            session.add(
                NotificationDelivery(
                    user_id=radar.user_id,
                    radar_id=radar.id,
                    signal_id=signal.id,
                    channel=NotificationChannel(channel_name),
                    status=DeliveryStatus.PENDING,
                    payload={"signal_id": signal.id, "radar": radar.name},
                    scheduled_for=last + delay,
                )
            )
            queued += 1

        match.notified_at = now
        radar.last_notified_at = now

    await session.commit()
    if queued:
        logger.info("queued %d notifications", queued)
async def flush_deliveries(session: AsyncSession, limit: int = 50) -> dict:
    """Send everything that is due. Failures are recorded, never fatal."""
    now = datetime.now(UTC)
    rows = (
        (
            await session.execute(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.status == DeliveryStatus.PENDING,
                    NotificationDelivery.scheduled_for <= now,
                )
                .order_by(NotificationDelivery.created_at)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    telegram = TelegramClient()
    sent = failed = 0

    for delivery in rows:
        delivery.attempts += 1
        signal = (
            await session.get(Signal, delivery.signal_id)
            if delivery.signal_id
            else None
        )
        if signal is None:
            delivery.status = DeliveryStatus.SKIPPED
            continue
        try:
            if delivery.channel == NotificationChannel.TELEGRAM:
                await _send_telegram(session, delivery, signal, telegram)
            else:
                await _send_push(session, delivery, signal)
            if delivery.status == DeliveryStatus.PENDING:
                delivery.status = DeliveryStatus.SENT
                delivery.sent_at = now
                sent += 1
        except Exception as exc:  # a failed send must never break the loop
            delivery.status = DeliveryStatus.FAILED
            delivery.error = str(exc)[:500]
            failed += 1
            logger.warning("delivery %s failed: %r", delivery.id, exc)

    await session.commit()
    return {"sent": sent, "failed": failed, "processed": len(rows)}
async def _send_telegram(session, delivery, signal, telegram) -> None:
    profile = (
        await session.execute(
            select(UserProfile).where(UserProfile.user_id == delivery.user_id)
        )
    ).scalar_one_or_none()
    if profile is None or not profile.telegram_chat_id:
        delivery.status = DeliveryStatus.SKIPPED
        delivery.error = "telegram chat_id not linked"
        return
    if not telegram.configured:
        delivery.status = DeliveryStatus.SKIPPED
        delivery.error = "TELEGRAM_BOT_TOKEN not configured"
        return
    await telegram.send(
        profile.telegram_chat_id,
        format_signal_alert(signal, delivery.payload.get("radar")),
    )


async def _send_push(session, delivery, signal) -> None:
    subscriptions = await _collect_subscriptions(session, delivery)
    if not subscriptions:
        delivery.status = DeliveryStatus.SKIPPED
        delivery.error = "no push subscriptions"
        return
    if not settings.vapid_private_key:
        delivery.status = DeliveryStatus.SKIPPED
        delivery.error = "VAPID keys not configured"
        return
    await send_web_push(
        subscriptions,
        format_web_push(signal, delivery.payload.get("radar")),
    )


async def _collect_subscriptions(session, delivery) -> list[dict]:
    subs: list[dict] = []
    prefs = (
        (
            await session.execute(
                select(NotificationPreference).where(
                    NotificationPreference.user_id == delivery.user_id,
                    NotificationPreference.radar_id == delivery.radar_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for pref in prefs:
        if not isinstance(pref.target, str):
            continue
        try:
            parsed = json.loads(pref.target)
        except ValueError:
            continue
        if isinstance(parsed, list):
            subs.extend(parsed)

    profile = (
        await session.execute(
            select(UserProfile).where(UserProfile.user_id == delivery.user_id)
        )
    ).scalar_one_or_none()
    if profile is not None and isinstance(profile.push_subscriptions, list):
        subs.extend(profile.push_subscriptions)
    return subs
    return queued
