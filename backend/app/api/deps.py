"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_session
from app.models import User
from app.models.enums import uuid_str
from app.models.user import UserProfile

bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_token(
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    access_cookie: str | None = Cookie(default=None, alias="access_token"),
) -> str | None:
    if bearer is not None and bearer.credentials:
        return bearer.credentials
    return access_cookie


async def _load_user(session: AsyncSession, user_id: str | None) -> User | None:
    """Fetch a user with the profile already loaded.

    Accessing ``user.profile`` later would otherwise trigger a lazy load from
    sync context, which async SQLAlchemy rejects with MissingGreenlet.
    """
    if not user_id:
        return None
    result = await session.execute(
        select(User).options(selectinload(User.profile)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def _ensure_local_user(session: AsyncSession) -> User:
    """Return the single local user, creating it on first use.

    This app runs on the operator's own machine, so there is nobody to log in
    as. Rather than leaving every personalised feature unreachable behind a login
    wall, the database gets one local account and every request uses it. Radars,
    saved signals and notifications therefore work out of the box, and there is
    no token, cookie or OAuth anywhere in the flow.

    Set `local_user_email` to change the identity; set `auth_disabled` to false to
    restore real token-based auth for a hosted deployment.
    """
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
    await session.commit()

    return (
        await session.execute(
            select(User)
            .options(selectinload(User.profile))
            .where(User.id == user.id)
        )
    ).scalar_one()


async def get_current_user(
    session: SessionDep,
    token: Annotated[str | None, Depends(get_token)] = None,
) -> User:
    if not settings.auth_disabled:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )
        user = await _load_user(session, payload.get("sub"))
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
            )
        return user

    return await _ensure_local_user(session)


async def get_optional_user(
    session: SessionDep,
    token: Annotated[str | None, Depends(get_token)] = None,
) -> User | None:
    """Resolve the user when a token is present, but never require one.

    Read endpoints use this so browsing signals is public while per-user flags
    (saved / ignored) are still personalised for signed-in visitors.
    """
    if settings.auth_disabled:
        return await _ensure_local_user(session)

    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user = await _load_user(session, payload.get("sub"))
    if user is None or not user.is_active:
        return None
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]