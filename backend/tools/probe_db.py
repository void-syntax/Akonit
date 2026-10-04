"""Tries the known Supabase connection-string shapes and reports which works.

The direct host does not resolve for this project, so the pooler is the only
route. Pooler auth depends on the username format and the port, so this tries
the combinations instead of guessing.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REF = "qtozkhuqaqnglztaalkx"
PASSWORD = "akonit3852105"
REGION = "eu-central-1"
POOLER = f"aws-0-{REGION}.pooler.supabase.com"
DIRECT = f"db.{REF}.supabase.co"

VARIANTS = [
    ("project domain 5432", f"{REF}.supabase.co", 5432, "postgres"),
    ("project domain 6543", f"{REF}.supabase.co", 6543, "postgres"),
    ("pooler 5432 user=postgres.<ref>", POOLER, 5432, f"postgres.{REF}"),
    ("pooler 6543 user=postgres.<ref>", POOLER, 6543, f"postgres.{REF}"),
    ("direct 5432", DIRECT, 5432, "postgres"),
]


async def probe(host: str, port: int, user: str) -> str:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = (
        f"postgresql+asyncpg://{user}:{PASSWORD}@{host}:{port}/postgres"
    )
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
            result = await conn.execute(
                text(
                    "select count(*) from information_schema.tables "
                    "where table_schema = 'public'"
                )
            )
            return f"OK (tables={result.scalar()})"
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {str(exc)[:120]}"
    finally:
        await engine.dispose()


async def main() -> int:
    winners = []
    for name, host, port, user in VARIANTS:
        status = await probe(host, port, user)
        print(f"{name:32} {status}")
        if status.startswith("OK"):
            winners.append(name)

    print()
    if winners:
        print("WORKING:")
        for name in winners:
            print(f"  {name}")
        return 0
    print("none of the variants worked")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))