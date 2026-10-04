"""Creates a local demo account so the UI can be explored end to end.

Prints the credentials. Nothing is written to the repository.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import User, UserProfile  # noqa: E402
from app.models.enums import NotificationFrequency  # noqa: E402

EMAIL = "demo@akonite.dev"
PASSWORD = "DemoRadar2026!"


async def main() -> int:
    async with SessionLocal() as session:
        existing = (
            (
                await session.execute(
                    select(User).where(User.email == EMAIL)
                )
            )
            .scalar_one_or_none()
        )

        if existing is None:
            user = User(
                email=EMAIL,
                password_hash=hash_password(PASSWORD),
                is_active=True,
            )
            session.add(user)
            await session.flush()

            session.add(
                UserProfile(
                    user_id=user.id,
                    display_name="Demo Operator",
                    default_frequency=NotificationFrequency.INSTANT,
                )
            )
            await session.commit()
            print("created")
        else:
            # Make sure the account stays usable across reruns.
            existing.password_hash = hash_password(PASSWORD)
            existing.is_active = True
            await session.commit()
            print("reset")

    print("")
    print(f"email:    {EMAIL}")
    print(f"password: {PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))