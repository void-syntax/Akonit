"""Notification preferences, push subscription and delivery history."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.secrets import decrypt_secret, encrypt_secret
from app.models import NotificationDelivery, NotificationPreference, Radar, UserProfile
from app.models.enums import DeliveryStatus, NotificationChannel
from app.schemas.api import ORMModel
from app.notifications.telegram import TelegramClient
from datetime import datetime

router = APIRouter(prefix="/notifications", tags=["notifications"])


class PreferenceOut(ORMModel):
    id: str
    radar_id: str
    channel: NotificationChannel
    enabled: bool
    target: str | None
    min_strength: float


class DeliveryOut(ORMModel):
    id: str
    radar_id: str | None
    signal_id: str | None
    channel: NotificationChannel
    status: DeliveryStatus
    error: str | None
    attempts: int
    sent_at: datetime | None
    created_at: datetime


@router.get("/push/public-key")
async def push_public_key():
    """VAPID public key; empty string means push is not configured yet."""
    return {"public_key": settings.vapid_public_key}


@router.get("/preferences", response_model=list[PreferenceOut])
async def list_preferences(session: SessionDep, user: CurrentUser):
    return (
        (
            await session.execute(
                select(NotificationPreference).where(
                    NotificationPreference.user_id == user.id
                )
            )
        )
        .scalars()
        .all()
    )


@router.put("/preferences", response_model=PreferenceOut)
async def upsert_preference(payload: dict, session: SessionDep, user: CurrentUser):
    radar_id = payload.get("radar_id")
    if not radar_id:
        raise HTTPException(status_code=400, detail="radar_id is required")

    try:
        channel = NotificationChannel(payload.get("channel", "WEB_PUSH"))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid channel")

    radar = (
        await session.execute(
            select(Radar).where(Radar.id == radar_id, Radar.user_id == user.id)
        )
    ).scalar_one_or_none()
    if radar is None:
        raise HTTPException(status_code=404, detail="Radar not found")
    row = (
        await session.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user.id,
                NotificationPreference.radar_id == radar_id,
                NotificationPreference.channel == channel,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = NotificationPreference(
            user_id=user.id, radar_id=radar_id, channel=channel
        )
        session.add(row)

    row.enabled = bool(payload.get("enabled", True))
    row.target = payload.get("target")
    row.min_strength = float(payload.get("min_strength") or 0)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(session: SessionDep, user: CurrentUser, limit: int = 50):
    return (
        (
            await session.execute(
                select(NotificationDelivery)
                .where(NotificationDelivery.user_id == user.id)
                .order_by(NotificationDelivery.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


@router.post("/push/subscribe")
async def subscribe_push(payload: dict, user: CurrentUser, session: SessionDep):
    """Register a browser push subscription for this user."""
    endpoint = payload.get("endpoint")
    keys = payload.get("keys") or {}
    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint is required")

    profile = user.profile
    if profile is None:
        profile = UserProfile(user_id=user.id)
        session.add(profile)

    subs = [
        s
        for s in (profile.push_subscriptions or [])
        if isinstance(s, dict) and s.get("endpoint") != endpoint
    ]
    subs.append({"endpoint": endpoint, "keys": keys})
    profile.push_subscriptions = subs
    await session.commit()
    return {
        "ok": True,
        "subscriptions": len(subs),
        "configured": bool(settings.vapid_private_key),
    }


@router.delete("/push/subscribe")
async def unsubscribe_push(payload: dict, user: CurrentUser, session: SessionDep):
    endpoint = payload.get("endpoint")
    profile = user.profile
    if profile is None:
        return {"ok": True, "subscriptions": 0}
    profile.push_subscriptions = [
        s
        for s in (profile.push_subscriptions or [])
        if isinstance(s, dict) and s.get("endpoint") != endpoint
    ]
    await session.commit()
    return {
        "ok": True,
        "subscriptions": len(profile.push_subscriptions),
        "configured": bool(settings.vapid_private_key),
    }


@router.get("/telegram/status")
async def telegram_status(user: CurrentUser):
    """Honest status: linked chat + whether the bot token is configured."""
    profile = user.profile
    return {
        "linked": bool(profile and profile.telegram_chat_id),
        "chat_id": profile.telegram_chat_id if profile else None,
        "alerts_enabled": bool(profile and profile.telegram_alerts_enabled),
        "bot_configured": bool(profile and profile.telegram_bot_token_encrypted)
        or bool(settings.telegram_bot_token),
        "push_configured": bool(settings.vapid_private_key),
    }


@router.put("/telegram/bot")
async def configure_telegram_bot(payload: dict, user: CurrentUser, session: SessionDep):
    token = str(payload.get("token") or "").strip()
    if not token or len(token) > 256 or ":" not in token:
        raise HTTPException(
            status_code=400, detail="Enter a valid token from @BotFather"
        )
    try:
        encrypted = encrypt_secret(token)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail="Telegram token encryption is not configured"
        ) from exc
    async with TelegramClient(token=token) as telegram:
        try:
            bot = await telegram.verify()
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail="Telegram rejected this bot token"
            ) from exc
    profile = user.profile
    if profile is None:
        profile = UserProfile(user_id=user.id)
        session.add(profile)
    profile.telegram_bot_token_encrypted = encrypted
    await session.commit()
    from app.bot.telegram_bot import notify_bot_config_changed

    notify_bot_config_changed()
    return {"ok": True, "bot_username": bot.get("username")}


@router.delete("/telegram/bot")
async def remove_telegram_bot(user: CurrentUser, session: SessionDep):
    profile = user.profile
    if profile:
        profile.telegram_bot_token_encrypted = None
        profile.telegram_alerts_enabled = False
        await session.commit()
        from app.bot.telegram_bot import notify_bot_config_changed

        notify_bot_config_changed()
    return {"ok": True}


@router.post("/telegram/test")
async def test_telegram(user: CurrentUser):
    profile = user.profile
    if not profile or not profile.telegram_chat_id:
        raise HTTPException(
            status_code=400, detail="Enter and save your Telegram chat ID first"
        )
    try:
        token = (
            decrypt_secret(profile.telegram_bot_token_encrypted)
            if profile.telegram_bot_token_encrypted
            else settings.telegram_bot_token
        )
        if not token:
            raise ValueError("No Telegram bot is configured")
        async with TelegramClient(token=token) as telegram:
            await telegram.send_test(profile.telegram_chat_id)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Test message failed; check that you started the bot and the chat ID is correct",
        ) from exc
    return {"ok": True}


@router.post("/telegram/find-chat")
async def find_telegram_chat(user: CurrentUser):
    profile = user.profile
    if profile and profile.telegram_chat_id:
        return {"chat_id": profile.telegram_chat_id, "name": None}
    if not profile or not profile.telegram_bot_token_encrypted:
        raise HTTPException(status_code=400, detail="Connect your Telegram bot first")
    try:
        token = decrypt_secret(profile.telegram_bot_token_encrypted)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail="Telegram bot token storage is unavailable"
        ) from exc
    from app.bot.telegram_bot import find_recent_private_chat

    result = find_recent_private_chat(token)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Open your saved bot in Telegram, press Start, then choose Find my chat again.",
        )
    chat_id, name = result
    return {"chat_id": chat_id, "name": name}


@router.post("/telegram/toggle")
async def toggle_telegram_alerts(enabled: bool, user: CurrentUser, session: SessionDep):
    profile = user.profile
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.telegram_alerts_enabled = enabled
    await session.commit()
    return {"ok": True, "telegram_alerts_enabled": profile.telegram_alerts_enabled}


@router.post("/telegram/link")
async def link_telegram(chat_id: str, user: CurrentUser, session: SessionDep):
    chat_id = chat_id.strip()
    try:
        int(chat_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="chat_id must be numeric")
    if len(chat_id) < 1 or len(chat_id) > 20:
        raise HTTPException(status_code=400, detail="chat_id length is invalid")
    profile = user.profile
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.telegram_chat_id = chat_id
    await session.commit()
    return {"ok": True, "telegram_chat_id": chat_id}
