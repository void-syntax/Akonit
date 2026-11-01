"""Shared FastAPI dependencies."""

from __future__ import annotations

import asyncio

from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_session
from app.models import User
from app.models.enums import uuid_str
from app.models.user import UserProfile

_LOCAL_USER_LOCK = asyncio.Lock()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _ensure_local_user(session: AsyncSession) -> User:
    """Return the single local user, creating it on first use.

    This app runs on the operator's own machine, so there is nobody to log in
    as. Rather than leaving every personalised feature unreachable behind a login
    wall, the database gets one local account and every request uses it. Radars,
    saved signals and notifications therefore work out of the box, and there is
    no token, cookie or OAuth anywhere in the flow.

    Set `local_user_email` to change the identity. Hosted authentication is not
    implemented; configuration rejects attempts to disable this local mode.
    """
    async with _LOCAL_USER_LOCK:
        return await _ensure_local_user_locked(session)


async def _ensure_local_user_locked(session: AsyncSession) -> User:
    email = settings.local_user_email
    existing = (
        await session.execute(
            select(User)
            .options(selectinload(User.profile))
            .where(User.email == email)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(
        id=uuid_str(),
        email=email,
        # No password is ever checked in local mode; the column stays non-null.
        password_hash="local",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    session.add(UserProfile(user_id=user.id))
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        existing = (
            await session.execute(
                select(User)
                .options(selectinload(User.profile))
                .where(User.email == email)
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing

    return (
        await session.execute(
            select(User)
            .options(selectinload(User.profile))
            .where(User.id == user.id)
        )
    ).scalar_one()


async def get_current_user(
    session: SessionDep,
) -> User:
    return await _ensure_local_user(session)


async def get_optional_user(
    session: SessionDep,
) -> User | None:
    """Return the local profile so public reads can personalize saved/ignored flags."""
    return await _ensure_local_user(session)


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
