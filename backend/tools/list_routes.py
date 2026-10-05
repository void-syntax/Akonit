"""List every route the app exposes, without needing the server running.

Also flags duplicate paths. Merging two handlers that both declared the same
route is an easy mistake to make and hard to spot by eye: FastAPI keeps the
first and silently ignores the second, so a rewritten endpoint can look present
in the source while the old version is still the one that answers.

    python -m tools.list_routes
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    from app.main import app

    rows: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        rows.append((path, ",".join(sorted(getattr(route, "methods", None) or {"-"}))))

    for path, methods in sorted(rows):
        print(f"{methods:22} {path}")
    print(f"\n{len(rows)} routes")

    # Compare path+method, not path alone: a GET and a PATCH on the same path are
    # two different endpoints, while the same method twice means one of them is
    # unreachable because FastAPI only ever dispatches to the first match.
    counts = Counter((path, m) for path, methods in rows for m in methods.split(","))
    duplicates = sorted(f"{m:6} {p}" for (p, m), n in counts.items() if n > 1)
    if not duplicates:
        print("no duplicate path+method pairs")
        return 0

    print(f"\nWARNING: {len(duplicates)} path+method(s) registered more than once:")
    for entry in duplicates:
        print(f"  {entry}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())