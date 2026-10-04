"""End-to-end check of the signed-in journey over real HTTP.

Registers nothing: it logs into the demo account, then walks radars, the radar
summary, notifications and custom tags. This is what a user would actually do
in the browser.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/v1"
EMAIL = "demo@akonite.dev"
PASSWORD = "DemoRadar2026!"

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def call(
    method: str, path: str, token: str | None = None, body: dict | None = None
) -> tuple[int, object]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def main() -> int:
    status, payload = call(
        "POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD}
    )
    token = (payload or {}).get("access_token") if isinstance(payload, dict) else None
    record("login works", status == 200 and bool(token), f"status={status}")
    if not token:
        print("cannot continue without a token")
        return 1

    status, profile = call("GET", "/auth/profile", token)
    record(
        "profile loads with settings fields",
        status == 200 and isinstance(profile, dict) and "signal_threshold" in profile,
        f"threshold={profile.get('signal_threshold') if isinstance(profile, dict) else 'n/a'}",
    )

    status, radars = call("GET", "/radars", token)
    radar_list = radars if isinstance(radars, list) else []
    record(
        "radars are listed",
        status == 200 and len(radar_list) > 0,
        f"count={len(radar_list)}",
    )

    if radar_list:
        radar_id = radar_list[0]["id"]

        status, summary = call("GET", f"/radars/{radar_id}/summary", token)
        parts = summary.get("parts", []) if isinstance(summary, dict) else []
        record(
            "radar summary is human readable",
            status == 200 and len(parts) > 0,
            f"parts={parts}",
        )

        status, matches = call(
            "GET", f"/signals?radar_id={radar_id}&limit=5", token
        )
        items = matches.get("items", []) if isinstance(matches, dict) else []
        record(
            "radar match query returns a page",
            status == 200 and "items" in (matches or {}),
            f"items={len(items)}",
        )

    status, conditions = call("GET", "/condition-types")
    record(
        "condition options load for the builder",
        status == 200 and isinstance(conditions, list) and len(conditions) > 0,
        f"types={len(conditions) if isinstance(conditions, list) else 'n/a'}",
    )

    status, tags = call("GET", "/custom-tags", token)
    record(
        "custom tags endpoint works",
        status == 200 and isinstance(tags, list),
        f"count={len(tags) if isinstance(tags, list) else 'n/a'}",
    )

    status, notes = call("GET", "/notifications/telegram/status", token)
    record(
        "telegram is configured",
        status == 200 and bool(notes.get("bot_configured")),
        f"bot={notes.get('bot_configured') if isinstance(notes, dict) else 'n/a'}",
    )

    status, key = call("GET", "/notifications/push/public-key")
    record(
        "vapid public key is served",
        status == 200 and bool(key.get("public_key")),
        f"key={'present' if key.get('public_key') else 'missing'}",
    )

    failures = [name for name, ok, _ in RESULTS if not ok]
    print("=" * 60)
    print(f"{len(RESULTS) - len(failures)}/{len(RESULTS)} checks passed")
    if failures:
        print("failed:", ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())