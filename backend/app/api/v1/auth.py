"""Identity and profile endpoints.

There is no authentication in the local build. The app runs on the operator's own
machine and resolves a single local account (see `app.api.deps`), so these
routes only answer "who am I" and "what are my settings". Registration, login,
passwords and OAuth are not implemented. Configuration rejects attempts to turn
off the local single-user mode so a missing login flow cannot be mistaken for
working hosted authentication.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.models.user import UserProfile
from app.schemas.api import ProfileOut, ProfileUpdate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    """Who the current request belongs to."""
    return UserOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/profile", response_model=ProfileOut)
async def profile(user: CurrentUser, session: SessionDep):
    """Settings for the local account, created on first read."""
    row = user.profile
    if row is None:
        row = UserProfile(user_id=user.id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(
    payload: ProfileUpdate, user: CurrentUser, session: SessionDep
):
    """Apply the settings changes the Settings screen submits."""
    row = user.profile
    if row is None:
        row = UserProfile(user_id=user.id)
        session.add(row)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return row
