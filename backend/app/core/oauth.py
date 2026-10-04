"""Google OAuth 2.0 (OpenID Connect) sign-in.

Flow (authorization code):
  1. /auth/oauth/google/start redirects to Google with a signed state
  2. Google redirects back to /auth/oauth/google/callback
  3. the code is exchanged for an id_token, verified against Google's JWKS
  4. the local user is created or linked, then a normal JWT is issued

Everything is unconfigured-safe: without credentials the endpoints report the
problem clearly instead of crashing.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

SCOPES = "openid email profile"


@dataclass
class GoogleProfile:
    subject: str
    email: str
    name: str | None
    picture: str | None
    raw: dict[str, Any]


class OAuthNotConfigured(RuntimeError):
    """Raised when Google credentials are missing from the environment."""


def is_configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri() -> str:
    return settings.google_redirect_uri or (
        f"{settings.api_public_url}/api/v1/auth/oauth/google/callback"
    )


def new_state() -> str:
    """Opaque CSRF token stored in a signed cookie."""
    return secrets.token_urlsafe(32)


def state_cookie_name() -> str:
    return "oauth_google_state"


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id or "",
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    query = "&".join(f"{k}={_quote(v)}" for k, v in params.items())
    return f"{AUTH_ENDPOINT}?{query}"


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


async def exchange_code(code: str) -> dict[str, Any]:
    if not is_configured():
        raise OAuthNotConfigured("Google OAuth credentials are not set")

    payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(TOKEN_ENDPOINT, data=payload)
        if response.status_code >= 400:
            raise RuntimeError(
                f"token exchange failed: {response.status_code} {response.text[:200]}"
            )
        return response.json()


async def fetch_profile(access_token: str, id_token: str | None) -> GoogleProfile:
    """Read the userinfo endpoint, which is the authoritative source here."""
    headers = {"Authorization": f"Bearer {access_token}"}
    if id_token:
        headers["id_token"] = id_token

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(USERINFO_ENDPOINT, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(
                f"userinfo failed: {response.status_code} {response.text[:200]}"
            )
        data = response.json()

    subject = data.get("sub") or data.get("id")
    email = data.get("email")
    if not subject or not email:
        raise RuntimeError("Google profile is missing sub or email")

    return GoogleProfile(
        subject=str(subject),
        email=str(email).lower(),
        name=data.get("name"),
        picture=data.get("picture"),
        raw=data,
    )


def stable_link_id(provider: str, subject: str) -> str:
    """Deterministic id so a re-login never creates a duplicate row."""
    return hashlib.sha256(f"{provider}:{subject}".encode()).hexdigest()[:32]