"""Emits the current schema as Postgres DDL.

Used to bootstrap a fresh database (Supabase included) without needing a direct
connection, and to review what a migration will actually do.
"""

import sys
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import Base  # noqa: E402

import app.models  # noqa: E402,F401  (registers every table)


def main() -> int:
    dialect = postgresql.dialect()
    parts: list[str] = []

    for name, table in sorted(Base.metadata.tables.items()):
        parts.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")

    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            parts.append(
                str(CreateIndex(index).compile(dialect=dialect)).strip() + ";"
            )

    sql = "\n\n".join(parts) + "\n"
    out = Path(__file__).resolve().parents[1] / "_schema_ddl.sql"
    out.write_text(sql, encoding="utf-8")

    print(f"tables: {len(Base.metadata.tables)}")
    print(f"statements: {len(parts)}")
    print(f"bytes: {len(sql)}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())