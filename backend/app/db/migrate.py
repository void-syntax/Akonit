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
        "telegram_chat_id": "VARCHAR(64)",
        "telegram_alerts_enabled": "BOOLEAN DEFAULT 0",
        "onboarded": "BOOLEAN DEFAULT 0",
        "default_frequency": "VARCHAR(32) DEFAULT 'instant'",
        "push_subscriptions": "JSON DEFAULT '[]'",
        "display_name": "VARCHAR(120)",
        "timezone": "VARCHAR(64) DEFAULT 'UTC'",
        "language": "VARCHAR(8) DEFAULT 'en'",
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
        "expires_at": "TIMESTAMP",
        "content_hash": "VARCHAR(64)",
    },
    "source_events": {"text_hash": "VARCHAR(16)"},
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

        # Keep the hash lookup cheap once event history grows. Index creation is
        # idempotent and does not rebuild or rewrite the existing SQLite table.
        if "source_events" in tables and "text_hash" in MIGRATIONS["source_events"]:
            await conn.execute(text(
                'CREATE INDEX IF NOT EXISTS "ix_source_events_text_hash" '
                'ON "source_events" ("text_hash")'
            ))

    return applied
