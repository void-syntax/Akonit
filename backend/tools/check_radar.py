"""Standalone check of the radar condition engine (no network calls)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal, engine, init_models
from app.models import RadarConditionGroup, Signal, User
from app.services.radar_service import (
    create_radar,
    groups_to_ast,
    radar_matches_signal,
)

CONDITIONS = {
    "op": "AND",
    "children": [
        {
            "op": "OR",
            "children": [
                {"type": "country", "operator": "IN", "value": ["KR", "JP"]}
            ],
        },
        {
            "op": "OR",
            "children": [
                {"type": "source", "operator": "IN", "value": ["tiktok", "youtube"]}
            ],
        },
        {"op": "NOT", "children": [{"type": "tag", "operator": "IN", "value": ["cosplay"]}]},
        {"type": "growth", "operator": "GT", "value": 100},
    ],
}


def make_signal(**overrides) -> Signal:
    data = dict(
        title="New kbeauty trend",
        description="Korean makeup tutorial",
        country_code="KR",
        source_id="tiktok",
        growth=250.0,
        current_activity=900.0,
        strength=80.0,
        status="RISING",
        keywords=["makeup", "tiktok-trends"],
        first_seen_at=datetime.now(UTC),
    )
    data.update(overrides)
    return Signal(**data)


async def main() -> int:
    await init_models()
    async with SessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.email == "radar-check@local")
            )
        ).scalar_one_or_none()
        if user is None:
            user = User(email="radar-check@local", password_hash="x")
            session.add(user)
            await session.commit()
            await session.refresh(user)

        radar = await create_radar(
            session,
            user_id=user.id,
            name="Korea Makeup",
            emoji="🇰🇷",
            conditions=CONDITIONS,
        )
        print(f"radar created: {radar.name}")
        print(f"  countries={radar.countries} sources={radar.source_ids}")

        groups = (
            (
                await session.execute(
                    select(RadarConditionGroup)
                    .where(RadarConditionGroup.radar_id == radar.id)
                    .options(selectinload(RadarConditionGroup.conditions))
                    .order_by(RadarConditionGroup.position)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        print(f"  persisted groups: {len(groups)}")
        for g in groups:
            print(
                f"    join={g.join_type.value:<4} exclude={str(g.is_exclude):<5}"
            )
            for c in g.conditions:
                print(f"       {c.condition_type.value} {c.operator.value} {c.value_json}")

        groups_to_ast(list(groups))
        print("  AST rebuilt from DB: OK")

        cases = [
            ("KR / tiktok / makeup / +250%", make_signal(), True),
            ("JP / tiktok / +250%", make_signal(country_code="JP"), True),
            ("US / tiktok (wrong country)", make_signal(country_code="US"), False),
            (
                "KR / github (wrong source)",
                make_signal(source_id="github"),
                False,
            ),
            (
                "KR / tiktok / cosplay excluded",
                make_signal(keywords=["makeup", "cosplay"]),
                False,
            ),
            ("KR / tiktok / growth 50% (<100)", make_signal(growth=50.0), False),
            ("KR / youtube / +250%", make_signal(source_id="youtube"), True),
        ]

        failures = 0
        for label, signal, expected in cases:
            matched, reason = await radar_matches_signal(session, radar, signal)
            ok = matched == expected
            failures += 0 if ok else 1
            print(
                f"  [{'PASS' if ok else 'FAIL'}] {label:<34} "
                f"-> matched={matched} ({reason})"
            )

    await engine.dispose()
    print()
    print("radar engine check:", "PASSED" if failures == 0 else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))