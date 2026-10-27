"""Telegram bot client. Short messages only, per the product spec."""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.pipeline.collectors.base import SourceUnavailable

logger = get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096
RETRY_ATTEMPTS = 3


class TelegramClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or settings.telegram_bot_token
        self._client = httpx.AsyncClient(
            timeout=settings.fetch_timeout_seconds,
            headers={"User-Agent": settings.http_user_agent},
        )

    @property
    def configured(self) -> bool:
        return bool(self.token)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> TelegramClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        await self.aclose()

    async def send(self, chat_id: str, text: str) -> None:
        if not self.token:
            raise SourceUnavailable("Telegram bot token is not configured")

        # Truncate to Telegram's max message length
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[: MAX_MESSAGE_LENGTH - 1] + "…"

        last_exc: Exception | None = None
        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = await self._client.post(
                    f"{TELEGRAM_API}/bot{self.token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": False,
                    },
                )

                # Fallback: if Markdown rendering fails (400), retry with HTML
                if response.status_code == 400:
                    logger.warning(
                        "Markdown render failed for %s, retrying with HTML",
                        chat_id,
                    )
                    response = await self._client.post(
                        f"{TELEGRAM_API}/bot{self.token}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": text,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": False,
                        },
                    )

                if response.status_code >= 400:
                    raise RuntimeError(
                        f"telegram {response.status_code}: {response.text[:200]}"
                    )

                logger.info("telegram message sent to %s", chat_id)
                return

            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < RETRY_ATTEMPTS - 1:
                    delay = 2**attempt  # exponential backoff: 1s, 2s
                    logger.warning(
                        "telegram network error (attempt %d/%d), retrying in %ds: %r",
                        attempt + 1,
                        RETRY_ATTEMPTS,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

        raise RuntimeError(
            f"telegram send failed after {RETRY_ATTEMPTS} attempts: {last_exc}"
        )

    async def verify(self) -> dict:
        """Validate this token and return safe, non-secret bot details."""
        if not self.token:
            raise ValueError("Telegram bot token is empty")
        response = await self._client.get(f"{TELEGRAM_API}/bot{self.token}/getMe")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Telegram returned an invalid response") from exc
        if response.status_code >= 400 or not payload.get("ok"):
            raise ValueError("Telegram rejected this bot token")
        bot = payload.get("result") or {}
        return {"username": bot.get("username"), "first_name": bot.get("first_name")}

    async def send_test(self, chat_id: str) -> None:
        await self.send(
            chat_id, "✅ Signal Radar: Telegram notifications are connected."
        )

    async def find_latest_private_chat(self) -> tuple[str, str | None] | None:
        """Find the latest private chat that sent this bot a message."""
        if not self.token:
            raise ValueError("Telegram bot token is empty")
        response = await self._client.get(
            f"{TELEGRAM_API}/bot{self.token}/getUpdates",
            params={"limit": 20, "allowed_updates": '["message"]'},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Telegram returned an invalid response") from exc
        if response.status_code >= 400 or not payload.get("ok"):
            raise ValueError("Telegram could not read bot updates")
        for update in reversed(payload.get("result") or []):
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            if chat.get("type") == "private" and chat.get("id") is not None:
                name = chat.get("first_name") or chat.get("username")
                return str(chat["id"]), name
        return None

    async def register_webhook(self, url: str) -> bool:
        if not self.token:
            return False
        response = await self._client.post(
            f"{TELEGRAM_API}/bot{self.token}/setWebhook",
            json={"url": url},
        )
        return response.status_code < 400
