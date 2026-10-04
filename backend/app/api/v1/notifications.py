"""Notification preferences, push subscription and delivery history."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.models import NotificationDelivery, NotificationPreference, UserProfile
from app.models.enums import DeliveryStatus, NotificationChannel
from app.schemas.api import ORMModel
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
async def upsert_preference(
    payload: dict, session: SessionDep, user: CurrentUser
):
    radar_id = payload.get("radar_id")
    if not radar_id:
        raise HTTPException(status_code=400, detail="radar_id is required")

    channel = NotificationChannel(payload.get("channel", "WEB_PUSH"))
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
        row = NotificationPreference(user_id=user.id, radar_id=radar_id, channel=channel)
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
async def subscribe_push(
    payload: dict, user: CurrentUser, session: SessionDep
):
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
async def unsubscribe_push(
    payload: dict, user: CurrentUser, session: SessionDep
):
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
        "bot_configured": bool(settings.telegram_bot_token),
        "push_configured": bool(settings.vapid_private_key),
    }


@router.post("/telegram/link")
async def link_telegram(chat_id: str, user: CurrentUser, session: SessionDep):
    profile = user.profile
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.telegram_chat_id = chat_id
    await session.commit()
    return {"ok": True, "telegram_chat_id": chat_id}