"""End-to-end verification with REAL data.

Runs the whole chain required by the brief:

    SOURCE -> REAL FETCH -> RAW EVENT -> NORMALIZATION -> DETECTION
           -> SIGNAL -> RADAR MATCH -> NOTIFICATION PAYLOAD

Usage: python -m tools.e2e_check
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Force UTF-8 output so emoji in titles never crash the run on Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal, engine, init_models  # noqa: E402
from app.models import (  # noqa: E402
    Radar,
    RadarCondition,
    RadarConditionGroup,
    Signal,
    SignalSnapshot,
    Source,
    SourceEvent,
    User,
)
from app.models.enums import NotificationFrequency  # noqa: E402
from app.notifications.formatter import format_signal_alert  # noqa: E402
from app.seed.runner import seed_countries, seed_sources, seed_tags  # noqa: E402
from app.services.pipeline_service import run_collection_cycle  # noqa: E402
from app.services.radar_service import create_radar, match_batch  # noqa: E402

COUNTRIES = ["US", "GB", "KR", "JP", "TR", "AE", "AZ"]

STATUS_ICON = {
    "ACTIVE": "[ACTIVE ]",
    "DEGRADED": "[DEGRADED]",
    "OFFLINE": "[OFFLINE ]",
    "OPTIONAL_CREDENTIALS": "[CREDS   ]",
}


def banner(text: str) -> None:
    print()
    print("=" * 74)
    print(text)
    print("=" * 74)


async def reset(session) -> None:
    for model in (
        SignalSnapshot,
        RadarCondition,
        RadarConditionGroup,
        SourceEvent,
        Signal,
        Radar,
        Source,
        User,
    ):
        await session.execute(delete(model))
    await session.commit()
async def run_fetch(session) -> None:
    banner("STEP 1  REAL FETCH from all sources")
    stats = await run_collection_cycle(
        session, countries=COUNTRIES, limit_per_source=25
    )
    print(f"fetched events  : {stats.fetched}")
    print(f"sources ok      : {stats.sources_ok}")
    print(f"sources failed  : {stats.sources_failed}")
    print(f"signals created : {stats.signals_created}")
    print(f"signals updated : {stats.signals_updated}")
    for err in stats.errors[:6]:
        print(f"  note: {err[:120]}")


async def run_health(session) -> None:
    banner("STEP 2  SOURCE HEALTH (honest status)")
    sources = (
        (await session.execute(select(Source).order_by(Source.priority)))
        .scalars()
        .all()
    )
    for src in sources:
        print(
            f"{STATUS_ICON[src.status.value]} {src.id:<20}"
            f"records={src.total_records:<5} strategy={src.strategy or '-'}"
        )
        if src.status_reason:
            print(f"                     reason: {src.status_reason[:96]}")


async def run_signals(session) -> list[Signal]:
    banner("STEP 3  SIGNALS produced by detection")
    signals = (
        (
            await session.execute(
                select(Signal).order_by(Signal.strength.desc()).limit(12)
            )
        )
        .scalars()
        .all()
    )
    for s in signals:
        print(
            f"[{s.status.value:<8}] str={s.strength:<6} "
            f"{s.country_code or 'GLOBAL':<6} {s.source_id:<18} {s.title[:42]}"
        )
        print(
            f"            activity={s.current_activity:,.0f} growth={s.growth:.0f}%"
            f"  tags={','.join((s.keywords or [])[:4])}"
        )
    total = (
        await session.execute(select(Signal.id))
    ).scalars().all()
    print(f"\ntotal signals stored: {len(total)} (top 12 shown)")
    return signals


async def run_history(session, signals: list[Signal]) -> None:
    banner("STEP 4  SNAPSHOT HISTORY (append-only)")
    snapshots = (
        (await session.execute(select(SignalSnapshot.id)))
    ).scalars().all()
    print(f"snapshots stored: {len(snapshots)}")
    if not signals:
        return
    history = (
        (
            await session.execute(
                select(SignalSnapshot)
                .where(SignalSnapshot.signal_id == signals[0].id)
                .order_by(SignalSnapshot.captured_at)
            )
        )
        .scalars()
        .all()
    )
    for snap in history[-5:]:
        print(
            f"   {snap.captured_at:%H:%M:%S} activity={snap.activity:,.0f} "
            f"growth={snap.growth:.0f}% strength={snap.strength}"
        )
RADAR_CONDITIONS = {
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
                {
                    "type": "source",
                    "operator": "IN",
                    "value": ["tiktok", "youtube", "google_trends"],
                }
            ],
        },
        {
            "op": "NOT",
            "children": [
                {"type": "tag", "operator": "IN", "value": ["cosplay"]}
            ],
        },
    ],
}


async def run_radar(session) -> None:
    banner("STEP 5  RADAR creation with AND / OR / EXCLUDE")
    user = User(email="e2e@radar.example.com", password_hash="x")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    radar = await create_radar(
        session,
        user_id=user.id,
        name="Korea Makeup",
        emoji="🇰🇷",
        conditions=RADAR_CONDITIONS,
        notification_frequency=NotificationFrequency.INSTANT,
    )
    print(f"radar: {radar.name} ({radar.id[:8]})")
    print(f"  countries : {radar.countries}")
    print(f"  sources   : {radar.source_ids}")

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
            f"    join={g.join_type.value:<4} exclude={str(g.is_exclude):<5} "
            f"conditions={len(g.conditions)}"
        )
        for c in g.conditions:
            print(
                f"       {c.condition_type.value} {c.operator.value} "
                f"{c.value_json}"
            )


async def run_matching(session) -> None:
    banner("STEP 6  RADAR MATCHING over real signals")
    outcomes = await match_batch(session, lookback_minutes=240)
    print(f"total matches: {len(outcomes)}")
    for outcome in outcomes[:10]:
        signal = await session.get(Signal, outcome.signal_id)
        print(f"  MATCH: {signal.title[:60]}")
        print(
            f"        country={signal.country_code} source={signal.source_id} "
            f"strength={signal.strength} tags={','.join((signal.keywords or [])[:3])}"
        )


async def run_notifications(session, signals: list[Signal]) -> None:
    banner("STEP 7  NOTIFICATION PAYLOAD (short format)")
    for signal in signals[:3]:
        print(format_signal_alert(signal))
        print("-" * 50)


async def main() -> int:
    import logging

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    print(f"database: {settings.database_url}")
    await init_models()

    async with SessionLocal() as session:
        banner("STEP 0  reset + seed")
        await reset(session)
        await seed_countries(session)
        await seed_tags(session)
        await seed_sources(session)

        await run_fetch(session)
        await run_health(session)
        signals = await run_signals(session)
        await run_history(session, signals)
        await run_radar(session)
        await run_matching(session)
        await run_notifications(session, signals)
        await session.commit()

    await engine.dispose()
    banner("E2E COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))