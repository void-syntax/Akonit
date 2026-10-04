"""Creates a demo radar with real matching conditions.

Gives a fresh account something to look at: the radar summary, the matching
signals and the notification queue all become observable immediately.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import Radar, User  # noqa: E402
from app.models.enums import NotificationFrequency  # noqa: E402
from app.services.radar_service import create_radar, match_batch  # noqa: E402

EMAIL = "demo@akonite.dev"

CONDITIONS: dict = {
    "op": "AND",
    "is_exclude": False,
    "children": [
        {"type": "COUNTRY", "operator": "IN", "value": ["KR", "JP", "US", "GB"]},
        {"type": "GROWTH", "operator": "GT", "value": 50},
    ],
}

RADARS = [
    (
        "Breakout Watch",
        "\U0001f525",
        {
            "op": "AND",
            "children": [
                {"type": "SOURCE", "operator": "IN", "value": ["tiktok", "youtube"]},
                {"type": "GROWTH", "operator": "GT", "value": 100},
            ],
        },
        40.0,
    ),
    (
        "Free AI Tools",
        "\U0001f916",
        {
            "op": "AND",
            "children": [
                {
                    "type": "SOURCE",
                    "operator": "IN",
                    "value": ["github", "huggingface", "hackernews", "producthunt"],
                },
                {"type": "STATUS", "operator": "IN", "value": ["NEW", "RISING"]},
            ],
        },
        35.0,
    ),
]


async def main() -> int:
    async with SessionLocal() as session:
        user = (
            (await session.execute(select(User).where(User.email == EMAIL)))
            .scalar_one_or_none()
        )
        if user is None:
            print("demo account missing; run tools.make_demo_account first")
            return 1

        existing = (
            (
                await session.execute(select(Radar).where(Radar.user_id == user.id))
            )
            .scalars()
            .all()
        )

        if existing:
            print(f"{len(existing)} radar(s) already exist")
        else:
            for name, emoji, conditions, threshold in RADARS:
                await create_radar(
                    session,
                    user_id=user.id,
                    name=name,
                    emoji=emoji,
                    conditions=conditions,
                    signal_threshold=threshold,
                    notification_frequency=NotificationFrequency.INSTANT,
                )
                print(f"created radar: {name}")

        outcomes = await match_batch(session, lookback_minutes=180)
        print(f"matches in lookback: {len(outcomes)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))