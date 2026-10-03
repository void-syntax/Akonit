"""Auth + profile endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import User, UserProfile
from app.schemas.api import (
    LoginRequest,
    ProfileOut,
    ProfileUpdate,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def _set_cookies(response: Response, tokens: TokenResponse) -> None:
    response.set_cookie(
        "access_token",
        tokens.access_token,
        httponly=True,
        samesite="lax",
        max_age=settings.access_token_ttl_minutes * 60,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        tokens.refresh_token,
        httponly=True,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
        path="/",
    )


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
async def register(payload: RegisterRequest, session: SessionDep, response: Response):
    from sqlalchemy import select

    existing = (
        await session.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(
        email=payload.email, password_hash=hash_password(payload.password)
    )
    session.add(user)
    await session.flush()

    profile = UserProfile(
        user_id=user.id,
        display_name=payload.display_name or payload.email.split("@")[0],
    )
    session.add(profile)
    user.profile = profile
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)

    tokens = TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
    _set_cookies(response, tokens)
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep, response: Response):
    from sqlalchemy import select

    user = (
        await session.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    user.last_login_at = datetime.now(UTC)
    await session.commit()

    tokens = TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
    _set_cookies(response, tokens)
    return tokens


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user


@router.get("/profile", response_model=ProfileOut)
async def profile(user: CurrentUser, session: SessionDep):
    profile = user.profile
    if profile is None:
        profile = UserProfile(user_id=user.id)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(
    payload: ProfileUpdate, user: CurrentUser, session: SessionDep
):
    profile = user.profile
    if profile is None:
        profile = UserProfile(user_id=user.id)
        session.add(profile)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    await session.commit()
    await session.refresh(profile)
    return profile