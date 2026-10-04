"""Fetches each page over HTTP and checks it actually rendered.

Catches the failure mode where a dev server serves a stale build: the old
markers would still be present, or a page would return an error.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000"

# path -> markers that must appear in the HTML
# Markers are chosen for what is genuinely server-rendered, since the live
# badge and the signed-in panels are client-side and depend on auth state.
PAGES: dict[str, list[str]] = {
    "/": ["SIGNAL RADAR", "Live signals", "RISING", "BREAKOUT"],
    "/discover": ["Discover"],
    "/radars": ["radar"],
    "/saved": ["Saved"],
    "/login": ["Sign in", "password"],
    # Auth is resolved on the client, so the server-rendered HTML shows the
    # hydration placeholder; the real content appears in the browser.
    "/settings": ["Loading"],
    "/profile": ["Loading"],
}

# markers from the old UI that must be gone
STALE = ["Set what you watch once", "🎯", "Sign in to start receiving early signals"]


def fetch(path: str) -> tuple[int, str]:
    url = f"{BASE}{path}"
    request = urllib.request.Request(url, headers={"User-Agent": "signal-radar-check"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def main() -> int:
    failures: list[str] = []

    for path, markers in PAGES.items():
        status, body = fetch(path)
        missing = [m for m in markers if m not in body]
        stale = [m for m in STALE if m in body]

        state = "OK" if status == 200 and not missing and not stale else "FAIL"
        if state == "FAIL":
            failures.append(path)

        print(f"[{state}] {path} status={status} bytes={len(body)}")
        if missing:
            print(f"        missing: {missing}")
        if stale:
            print(f"        stale markup: {stale}")

    service_worker = fetch("/sw.js")
    print(
        f"[{'OK' if service_worker[0] == 200 else 'FAIL'}] /sw.js "
        f"status={service_worker[0]}"
    )
    if service_worker[0] != 200:
        failures.append("/sw.js")

    print("=" * 60)
    print(f"{len(PAGES) + 1 - len(failures)}/{len(PAGES) + 1} pages OK")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())