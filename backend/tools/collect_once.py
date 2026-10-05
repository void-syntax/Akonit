"""Run one collection cycle against a throwaway database.

Answers the only question that matters on a fresh machine: does the engine
actually produce a usable feed? No Docker, no Postgres and no prior state, so a
green run here means a clone will work too.

    python -m tools.collect_once
    python -m tools.collect_once --keep   # reuse signal_radar.db instead
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The database URL must be chosen before anything imports `app.db.session`,
# which builds its engine at import time. Setting it afterwards is silently
# ignored and the tool quietly talks to the wrong database.
if "--keep" in sys.argv:
    # Keep the data between runs so a second cycle can measure growth.
    # Defaults to SQLite so this needs no server; set DATABASE_URL yourself to
    # point it at the Postgres from docker compose.
    os.environ.setdefault(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{Path('signal_radar.db').as_posix()}",
    )
else:
    # A smoke test must never touch real data, so it gets its own file.
    smoke = Path(tempfile.gettempdir()) / "signal_radar_smoke.db"
    if smoke.exists():
        smoke.unlink()
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{smoke.as_posix()}"

import json  # noqa: E402

from tools._bootstrap import run as bootstrap_run  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.services.pipeline_service import run_collection_cycle  # noqa: E402
from app.workers.tasks import active_countries, collection_keywords  # noqa: E402


async def main() -> int:
    from sqlalchemy import func, select

    from app.models import Signal

    async with SessionLocal() as session:
        countries = await active_countries(session)
        keywords = await collection_keywords(session)
        stats = await run_collection_cycle(
            session,
            countries=countries,
            keywords=keywords,
            limit_per_source=40,
        )
        await session.commit()

        total = (
            await session.execute(select(func.count()).select_from(Signal))
        ).scalar_one()
        # Growth is only meaningful once a signal has two measurements, so a
        # brand new database legitimately has none. Counting them makes the
        # difference between "the engine is broken" and "the engine is new"
        # visible instead of guessed at.
        with_growth = (
            await session.execute(
                select(func.count()).select_from(Signal).where(Signal.growth != 0.0)
            )
        ).scalar_one()
        by_status = (
            await session.execute(
                select(Signal.status, func.count()).group_by(Signal.status)
            )
        ).all()

    summary = {
        "countries": countries,
        "keywords": keywords,
        "fetched": stats.fetched,
        "signals_created": stats.signals_created,
        "signals_updated": stats.signals_updated,
        "sources_ok": stats.sources_ok,
        "sources_failed": stats.sources_failed,
        "signals_in_feed": total,
        "signals_with_measured_growth": with_growth,
        "by_status": {
            (getattr(s, "value", str(s))): n for s, n in by_status
        },
        "errors": stats.errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if stats.fetched == 0 or total == 0:
        print("\nFAIL: the engine fetched nothing. The feed would stay empty.")
        return 1

    print(f"\nOK: {total} signals in the feed.")
    if with_growth == 0:
        print(
            "Note: no signal has measurable growth yet. That is expected on the\n"
            "first cycle: growth needs two measurements to compare. Run this again\n"
            "in a minute and the second run will have a baseline."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(bootstrap_run(main()))