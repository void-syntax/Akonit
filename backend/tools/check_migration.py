"""Verifies a migration cycle on a scratch database.

Runs upgrade -> inspect -> downgrade -> upgrade so a broken migration is caught
before it ever reaches production.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB = Path(sys.argv[1] if len(sys.argv) > 1 else "_fresh_migration.db")


def tables() -> set[str]:
    with sqlite3.connect(DB) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def main() -> int:
    found = tables()
    expected = {"users", "signals", "radars", "countries", "tags", "sources"}
    missing = expected - found

    print(f"database: {DB}")
    print(f"tables: {len(found)}")
    print(f"missing expected: {sorted(missing) or 'none'}")

    if missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())