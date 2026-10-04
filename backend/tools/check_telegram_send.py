"""Sends a real test message through the notification dispatcher.

Proves the whole Telegram path works with the configured bot, rather than just
proving the token is syntactically valid.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import Signal, User, UserProfile  # noqa: E402
from app.notifications.formatter import format_signal_alert  # noqa: E402
from app.notifications.telegram import TelegramClient  # noqa: E402

CHAT_ID = "8844908509"


async def main() -> int:
    async with SessionLocal() as session:
        # selectinload avoids a lazy load of user.profile from sync context.
        user = (
            (
                await session.execute(
                    select(User)
                    .options(selectinload(User.profile))
                    .where(User.email == "demo@akonite.dev")
                )
            )
            .scalar_one_or_none()
        )
        if user is None:
            print("demo account missing")
            return 1

        profile = user.profile
        if profile is None:
            profile = UserProfile(user_id=user.id)
            session.add(profile)
        profile.telegram_chat_id = CHAT_ID
        await session.commit()

        signal = (
            (await session.execute(select(Signal).order_by(Signal.strength.desc())))
            .scalars()
            .first()
        )

        if signal is None:
            print("no signal available to send")
            return 1

        message = format_signal_alert(signal)
        client = TelegramClient()

        if not client.configured:
            print("TELEGRAM_BOT_TOKEN is not configured")
            return 1

        try:
            await client.send(CHAT_ID, message)
        except Exception as exc:  # noqa: BLE001
            print(f"send failed: {exc}")
            return 1
        finally:
            await client.aclose()

        print(f"sent to chat {CHAT_ID}")
        print(f"signal: {signal.title[:70]}")
        print("telegram delivery: OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))