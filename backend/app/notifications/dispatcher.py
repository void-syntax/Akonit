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
from app.notifications.webhook_dispatcher import dispatch_webhook_notification

logger = get_logger(__name__)

# Sentinel for radars that have never notified: everything is due immediately.
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

FREQUENCY_DELAY = {
    NotificationFrequency.INSTANT: timedelta(0),
    NotificationFrequency.EVERY_15_MIN: timedelta(minutes=15),
    NotificationFrequency.HOURLY: timedelta(hours=1),
    NotificationFrequency.DAILY_DIGEST: timedelta(days=1),
}


def aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes while `now` is UTC-aware.

    Comparing the two raises TypeError, so every timestamp read from the
    database goes through here first.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def notify_matches(
    session: AsyncSession,
    *,
    signal_ids: list[str] | None = None,
    radar_id: str | None = None,
    now: datetime | None = None,
) -> int:
    """Queue deliveries for every radar match that is due. Returns the count.

    N+1 elimination: signals and radars are fetched in two bulk queries keyed
    by the match rows; no per-match ``session.get()`` calls are made.
    """
    now = now or datetime.now(UTC)
    statement = select(RadarSignal).where(RadarSignal.notified_at.is_(None))
    if radar_id:
        statement = statement.where(RadarSignal.radar_id == radar_id)
    if signal_ids:
        statement = statement.where(RadarSignal.signal_id.in_(signal_ids))

    matches = (await session.execute(statement)).scalars().all()
    if not matches:
        return 0

    # ── Bulk-load signals and radars referenced by the match rows ─────────────
    match_signal_ids = list({m.signal_id for m in matches})
    match_radar_ids = list({m.radar_id for m in matches})

    signals_by_id: dict[str, Signal] = {
        s.id: s
        for s in (
            await session.execute(select(Signal).where(Signal.id.in_(match_signal_ids)))
        )
        .scalars()
        .all()
    }
    radars_by_id: dict[str, Radar] = {
        r.id: r
        for r in (
            await session.execute(select(Radar).where(Radar.id.in_(match_radar_ids)))
        )
        .scalars()
        .all()
    }

    queued = 0

    for match in matches:
        if match.is_dismissed:
            continue
        signal = signals_by_id.get(match.signal_id)
        radar = radars_by_id.get(match.radar_id)
        if signal is None or radar is None:
            continue
        if signal.status == SignalStatus.FADING or not radar.is_active:
            continue

        delay = FREQUENCY_DELAY.get(radar.notification_frequency, timedelta(0))
        last = aware(radar.last_notified_at) or EPOCH
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

    if hasattr(session, "flush"):
        await session.flush()
    if queued:
        logger.info("queued %d notifications", queued)
    return queued
async def flush_deliveries(session: AsyncSession, limit: int = 50) -> dict:
    """Send everything that is due. Failures are recorded, never fatal.

    N+1 elimination: after fetching the delivery rows, all referenced Signal
    rows and UserProfile rows are fetched in two bulk queries and cached in
    dicts keyed by id.  The per-delivery loop then does only in-memory lookups.
    """
    now = datetime.now(UTC)

    pending_q = (
        select(NotificationDelivery)
        .where(
            NotificationDelivery.status == DeliveryStatus.PENDING,
            NotificationDelivery.scheduled_for <= now,
        )
    )
    failed_q = (
        select(NotificationDelivery)
        .where(
            NotificationDelivery.status == DeliveryStatus.FAILED,
            NotificationDelivery.attempts < 3,
        )
    )

    pending_rows = (await session.execute(pending_q.order_by(NotificationDelivery.created_at).limit(limit))).scalars().all()
    failed_rows = (await session.execute(failed_q.order_by(NotificationDelivery.created_at).limit(limit))).scalars().all()

    # Merge, deduplicate by id, preserve order (pending first)
    seen_ids: set = set()
    rows = []
    for row in list(pending_rows) + list(failed_rows):
        if row.id not in seen_ids:
            seen_ids.add(row.id)
            rows.append(row)
    rows = rows[:limit]

    if not rows:
        return {"sent": 0, "failed": 0, "processed": 0}

    # ── Bulk-load signals and user profiles referenced by the delivery rows ───
    delivery_signal_ids = list({d.signal_id for d in rows if d.signal_id})
    delivery_user_ids = list({d.user_id for d in rows if d.user_id})

    signals_cache: dict[str, Signal] = {}
    if delivery_signal_ids:
        signals_cache = {
            s.id: s
            for s in (
                await session.execute(
                    select(Signal).where(Signal.id.in_(delivery_signal_ids))
                )
            )
            .scalars()
            .all()
        }

    profiles_cache: dict[str, UserProfile] = {}
    if delivery_user_ids:
        profiles_cache = {
            p.user_id: p
            for p in (
                await session.execute(
                    select(UserProfile).where(UserProfile.user_id.in_(delivery_user_ids))
                )
            )
            .scalars()
            .all()
        }

    sent = failed = 0

    async with TelegramClient() as telegram:
        for delivery in rows:
            # FAILED deliveries that hit the attempt cap get skipped instead of retried
            if delivery.status == DeliveryStatus.FAILED and delivery.attempts >= 3:
                delivery.status = DeliveryStatus.SKIPPED
                continue

            delivery.attempts += 1
            signal = signals_cache.get(delivery.signal_id) if delivery.signal_id else None
            if signal is None:
                delivery.status = DeliveryStatus.SKIPPED
                continue
            try:
                if delivery.channel == NotificationChannel.TELEGRAM:
                    await _send_telegram_cached(session, delivery, signal, telegram, profiles_cache)
                elif delivery.channel in (NotificationChannel.DISCORD, NotificationChannel.SLACK, NotificationChannel.WEBHOOK):
                    await dispatch_webhook_notification(session, delivery, signal)
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

    if hasattr(session, "flush"):
        await session.flush()
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
    if not profile.telegram_alerts_enabled:
        delivery.status = DeliveryStatus.SKIPPED
        delivery.error = "telegram alerts disabled by user"
        return
    if not telegram.configured:
        delivery.status = DeliveryStatus.SKIPPED
        delivery.error = "TELEGRAM_BOT_TOKEN not configured"
        return
    await telegram.send(
        profile.telegram_chat_id,
        format_signal_alert(signal, delivery.payload.get("radar")),
    )


async def _send_telegram_cached(
    session,
    delivery,
    signal,
    telegram,
    profiles_cache: dict,
) -> None:
    """Like ``_send_telegram`` but uses an already-loaded profile dict."""
    profile = profiles_cache.get(delivery.user_id)
    if profile is None:
        # Fall back to a DB query if somehow the profile wasn't pre-loaded.
        profile = (
            await session.execute(
                select(UserProfile).where(UserProfile.user_id == delivery.user_id)
            )
        ).scalar_one_or_none()
    if profile is None or not profile.telegram_chat_id:
        delivery.status = DeliveryStatus.SKIPPED
        delivery.error = "telegram chat_id not linked"
        return
    if not profile.telegram_alerts_enabled:
        delivery.status = DeliveryStatus.SKIPPED
        delivery.error = "telegram alerts disabled by user"
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

    # Deduplicate by endpoint URL; keep first occurrence of each
    seen_endpoints: set[str] = set()
    unique_subs: list[dict] = []
    for sub in subs:
        if not isinstance(sub, dict):
            continue
        endpoint = sub.get("endpoint", "")
        if endpoint and endpoint not in seen_endpoints:
            seen_endpoints.add(endpoint)
            unique_subs.append(sub)
        elif not endpoint:
            unique_subs.append(sub)
    return unique_subs
