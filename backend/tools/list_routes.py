"""Lists every API route from the live OpenAPI schema."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def main() -> int:
    with urllib.request.urlopen(f"{BASE}/openapi.json", timeout=30) as response:
        schema = json.loads(response.read().decode("utf-8"))

    paths = schema.get("paths", {})
    print(f"total routes: {len(paths)}\n")

    for route in sorted(paths):
        methods = ",".join(sorted(m.upper() for m in paths[route]))
        print(f"{methods:22} {route}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())