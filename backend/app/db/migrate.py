"""Lightweight, idempotent schema migrations for SQLite.

SQLite cannot ALTER TABLE ... ADD COLUMN with a non-constant default, and the
product settings fields were added after the first databases were created.
`apply_migrations` adds any missing column so an existing database keeps working
without a manual reset.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# table -> column definitions that may be missing in an older database
MIGRATIONS: dict[str, dict[str, str]] = {
    "user_profiles": {
        "signal_threshold": "FLOAT DEFAULT 0.0",
        "default_countries": "JSON DEFAULT '[]'",
        "default_sources": "JSON DEFAULT '[]'",
        "default_tags": "JSON DEFAULT '[]'",
        "quiet_hours": "JSON",
        "theme": "VARCHAR(16) DEFAULT 'dark'",
    },
    "custom_tags": {
        "aliases": "JSON DEFAULT '[]'",
        "exclude_hashtags": "JSON DEFAULT '[]'",
        "exclude_countries": "JSON DEFAULT '[]'",
    },
    "signals": {
        "velocity": "FLOAT DEFAULT 0.0",
        "density_count": "INTEGER DEFAULT 1",
        "matched_at": "TIMESTAMP",
        "tags_updated_at": "TIMESTAMP",
    },
}


async def apply_migrations(engine: AsyncEngine) -> list[str]:
    """Add missing columns in place. Returns the list of applied changes."""
    applied: list[str] = []

    async with engine.begin() as conn:
        tables = {
            row[0]
            for row in (await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )).all()
        }

        for table, columns in MIGRATIONS.items():
            if table not in tables:
                continue

            info = await conn.execute(text(f'PRAGMA table_info("{table}")'))
            existing = {row[1] for row in info.all()}

            for column, ddl in columns.items():
                if column in existing:
                    continue
                await conn.execute(
                    text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}')
                )
                applied.append(f"{table}.{column}")

    return applied