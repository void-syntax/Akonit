"""Environment hygiene for the local build.

Two classes of problem are checked, both of which have shipped real bugs here:

1. A variable documented in .env.example that Settings never reads. It looks
   like a working knob and silently does nothing.
2. A leftover hosted-service URL in a local .env. This overrides the local
   default and sends every query to someone else's database, which fails with an
   error that has nothing to do with the code.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent

CONFIG = BACKEND / "app" / "core" / "config.py"
ENV_EXAMPLES = [ROOT / ".env.example", BACKEND / ".env.example"]

# Hosts that only make sense for a hosted deployment.
CLOUD_HOSTS = ("supabase.co", "pooler.supabase", "vercel.app", "onrender.com")


def settings_fields() -> set[str]:
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    fields: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields.add(node.target.id)

    return fields


def env_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.append(line.split("=", 1)[0].strip().lstrip("#").strip())
    return keys


def check_documented(fields: set[str]) -> int:
    """Every documented key must be a real setting."""
    known = {f.lower() for f in fields}
    problems = 0

    for path in ENV_EXAMPLES:
        if not path.exists():
            continue
        missing = sorted(k for k in env_keys(path) if k.lower() not in known)
        relative = path.relative_to(ROOT)
        if missing:
            print(f"{relative}: documented but not read by Settings")
            for key in missing:
                print(f"  - {key}")
            problems += len(missing)

    if not problems:
        print("env.example keys all map to real settings")
    return problems


def check_local_env() -> int:
    """A local .env must not point at a hosted service."""
    problems = 0
    for path in (ROOT / ".env", BACKEND / ".env"):
        if not path.exists():
            continue
        hits = []
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for host in CLOUD_HOSTS:
                if host in stripped:
                    hits.append(f"  line {number}: {host}")
        if hits:
            print(f"{path.relative_to(ROOT)}: points at a hosted service")
            hits.extend(hits)
            print("\n".join(hits))
            print("  local builds must use localhost or a sqlite file")
            problems += len(hits)
    return problems


def check_migration_covers_models() -> int:
    """Every mapped column must exist in the Alembic migration.

    `init_models()` creates SQLite tables straight from the models, so a local
    SQLite run always matches. Postgres is migrated by Alembic, and a column that
    was added to a model but never to a migration is invisible until the query
    fails at runtime with "no such column" - deep inside a collection cycle,
    once per event, with no clue as to why.
    """
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    import app.models  # noqa: F401  (importing registers every table)
    from app.db.session import Base

    versions = list((BACKEND / "alembic" / "versions").glob("*.py"))
    if not versions:
        print("no migrations found; skipping column check")
        return 0

    text = "\n".join(v.read_text(encoding="utf-8") for v in versions)

    problems = 0
    for table in Base.metadata.sorted_tables:
        # create_table calls name the table; anything else is created implicitly.
        if f"'{table.name}'" not in text and f'"{table.name}"' not in text:
            print(f"table not in any migration: {table.name}")
            problems += 1
            continue
        for column in table.columns:
            if f"'{column.name}'" in text or f'"{column.name}"' in text:
                continue
            print(f"column missing from migrations: {table.name}.{column.name}")
            problems += 1

    if not problems:
        print("migrations cover every mapped column")
    return problems


def main() -> int:
    fields = settings_fields()
    print(f"settings fields: {len(fields)}")

    problems = (
        check_documented(fields) + check_local_env() + check_migration_covers_models()
    )
    if problems:
        print(f"\n{problems} problem(s) found")
        return 1

    print("environment looks clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())