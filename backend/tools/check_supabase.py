"""Checks that the configured Postgres is reachable and reports its state.

Reads DATABASE_URL from the environment or .env, so the password never has to
appear in a command line or in this file.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND = Path(__file__).resolve().parents[1]


def database_url() -> str:
    env_file = BACKEND / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    return os.environ.get("DATABASE_URL", "")


def masked(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


async def probe() -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = database_url()
    print(f"url: {masked(url)}")

    if url.startswith("sqlite"):
        print("database: SQLite (local)")
        return 0

    print("database: Postgres")
    engine = create_async_engine(url, pool_size=2, max_overflow=0)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("select version()"))
            print(f"connected: {result.scalar().split(',')[0]}")

            result = await conn.execute(
                text(
                    "select count(*) from information_schema.tables "
                    "where table_schema = 'public'"
                )
            )
            tables = result.scalar()
            print(f"public tables: {tables}")

            result = await conn.execute(
                text(
                    "select count(*) from pg_tables "
                    "where schemaname = 'public' and rowsecurity"
                )
            )
            print(f"tables with RLS: {result.scalar()}")

            if tables:
                result = await conn.execute(text("select count(1) from signals"))
                print(f"signals: {result.scalar()}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1
    finally:
        await engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(probe()))