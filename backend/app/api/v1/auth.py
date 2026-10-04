"""Auth + profile endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.core import oauth
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import OAuthAccount, User, UserProfile
from app.schemas.api import (
    LoginRequest,
    ProfileOut,
    ProfileUpdate,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

logger = get_logger(__name__)

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


# --------------------------------------------------------------------------
# Google OAuth
# --------------------------------------------------------------------------


@router.get("/oauth/google/start")
async def google_start(response: Response):
    """Redirect the browser to Google's consent screen."""
    from fastapi.responses import RedirectResponse

    if not oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Google sign-in is not configured. Set GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET in the environment."
            ),
        )

    state = oauth.new_state()
    response.set_cookie(
        oauth.state_cookie_name(),
        state,
        httponly=True,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return RedirectResponse(oauth.build_authorize_url(state))


@router.get("/oauth/status")
async def google_status():
    """Lets the UI hide the button instead of offering a broken flow."""
    return {
        "configured": oauth.is_configured(),
        "provider": "google",
        "redirect_uri": oauth.redirect_uri() if oauth.is_configured() else None,
    }


@router.get("/oauth/google/callback")
async def google_callback(
    request: Request,
    session: SessionDep,
    response: Response,
):
    """Exchange the code, then create or link the local account."""
    from fastapi.responses import RedirectResponse
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    if not oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=request.query_params.get("error", "missing authorization code"),
        )

    expected_state = request.cookies.get(oauth.state_cookie_name())
    received_state = request.query_params.get("state")
    if not expected_state or received_state != expected_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state mismatch, please try again",
        )

    try:
        token_payload = await oauth.exchange_code(code)
        profile = await oauth.fetch_profile(
            token_payload.get("access_token", ""),
            token_payload.get("id_token"),
        )
    except oauth.OAuthNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("google oauth failed: %r", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Google sign-in failed: {exc}",
        ) from exc

    link = (
        await session.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == "google",
                OAuthAccount.provider_user_id == profile.subject,
            )
        )
    ).scalar_one_or_none()

    if link is not None:
        user = (
            await session.execute(
                select(User)
                .options(selectinload(User.profile))
                .where(User.id == link.user_id)
            )
        ).scalar_one_or_none()
    else:
        # Link by verified email so signing in with Google joins an existing
        # account instead of creating a duplicate.
        user = (
            await session.execute(
                select(User)
                .options(selectinload(User.profile))
                .where(User.email == profile.email)
            )
        ).scalar_one_or_none()

        if user is None:
            user = User(
                email=profile.email,
                # Google-only account: store an unusable, non-guessable hash so
                # the account can never be logged into with a password.
                password_hash="oauth:" + oauth.stable_link_id(
                    "google", profile.subject
                ),
                is_active=True,
            )
            session.add(user)
            await session.flush()

            session.add(
                UserProfile(user_id=user.id, display_name=profile.name)
            )

        session.add(
            OAuthAccount(
                user_id=user.id,
                provider="google",
                provider_user_id=profile.subject,
                email=profile.email,
                name=profile.name,
                avatar_url=profile.picture,
                raw=profile.raw,
            )
        )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    user.last_login_at = datetime.now(UTC)
    await session.commit()

    tokens = TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
    _set_cookies(response, tokens)
    response.delete_cookie(oauth.state_cookie_name(), path="/")

    # Hand the token to the SPA, which stores it and redirects home.
    fragment = f"#access_token={tokens.access_token}"
    frontend = settings.frontend_url.rstrip("/")
    return RedirectResponse(f"{frontend}/auth/callback{fragment}", status_code=302)


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