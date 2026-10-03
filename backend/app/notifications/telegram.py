"""Telegram bot client. Short messages only, per the product spec."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.pipeline.collectors.base import SourceUnavailable

logger = get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org"


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

    async def send(self, chat_id: str, text: str) -> None:
        if not self.token:
            raise SourceUnavailable("Telegram bot token is not configured")
        response = await self._client.post(
            f"{TELEGRAM_API}/bot{self.token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"telegram {response.status_code}: {response.text[:200]}"
            )
        logger.info("telegram message sent to %s", chat_id)

    async def register_webhook(self, url: str) -> bool:
        if not self.token:
            return False
        response = await self._client.post(
            f"{TELEGRAM_API}/bot{self.token}/setWebhook",
            json={"url": url},
        )
        return response.status_code < 400