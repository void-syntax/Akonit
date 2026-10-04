"""Seed countries, tags and sources.

Safe to run on every schedule tick: the seeders are idempotent, so this only
inserts what is genuinely missing.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools._bootstrap import run as bootstrap_run  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.seed.runner import seed_countries, seed_sources, seed_tags  # noqa: E402


async def main() -> int:
    async with SessionLocal() as session:
        await seed_countries(session)
        await seed_tags(session)
        await seed_sources(session)
    print("reference data seeded (countries, tags, sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(bootstrap_run(main()))