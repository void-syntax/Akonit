"""Compares .env.example against the actual Settings model.

A variable documented but not read is worse than undocumented: it looks like a
feature and silently does nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent

CONFIG = BACKEND / "app" / "core" / "config.py"
ENV_EXAMPLE = ROOT / ".env.example"


def settings_fields() -> set[str]:
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    fields: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields.add(node.target.id)

    return fields


def env_keys() -> list[str]:
    keys: list[str] = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.append(line.split("=", 1)[0].strip().lstrip("#").strip())
    return keys


def main() -> int:
    fields = settings_fields()
    keys = env_keys()

    missing = sorted(k for k in keys if k.lower() not in {f.lower() for f in fields})

    print(f"settings fields: {len(fields)}")
    print(f"env.example keys: {len(keys)}")
    print("documented but not read by Settings:")
    for key in missing:
        print(f"  - {key}")
    if not missing:
        print("  (none)")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())