"""Live end-to-end check against the running servers.

Exercises the real HTTP path the product uses:
  sign up -> create radar -> conditions -> signals -> save -> history -> web UI.

Usage: python -m tools.live_check
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "http://localhost:8000/api/v1"
WEB = "http://localhost:3000"

LINES: list[str] = []


def log(message: str) -> None:
    LINES.append(message)
    Path("live_report.txt").write_text("\n".join(LINES), encoding="utf-8")


def call(
    method: str, url: str, body: dict | None = None, token: str | None = None
) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "SignalRadarLiveCheck/0.1")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read().decode()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:300]
    except Exception as exc:
        return 0, str(exc)


def check_web(path: str) -> None:
    try:
        with urllib.request.urlopen(f"{WEB}{path}", timeout=30) as response:
            size = len(response.read())
        log(f"WEB  {path:<14} -> {response.status} ({size} bytes)")
    except Exception as exc:
        log(f"WEB  {path:<14} -> ERR {exc}")


RADAR_BODY = {
    "name": "Korea Makeup",
    "emoji": "🇰🇷",
    "conditions": {
        "op": "AND",
        "children": [
            {"op": "OR", "children": [
                {"type": "country", "operator": "IN", "value": ["KR", "JP"]}
            ]},
            {"op": "OR", "children": [
                {"type": "source", "operator": "IN",
                 "value": ["tiktok", "youtube", "google_trends"]}
            ]},
            {"op": "NOT", "children": [
                {"type": "tag", "operator": "IN", "value": ["cosplay"]}
            ]},
            {"type": "growth", "operator": "GT", "value": 0},
        ],
    },
    "notification_frequency": "INSTANT",
}

CUSTOM_TAG_BODY = {
    "name": "Korean Makeup",
    "keywords": ["korean makeup", "k-beauty", "glass skin"],
    "hashtags": ["kbeauty", "glassskin"],
    "country_codes": ["KR"],
    "source_ids": ["tiktok", "youtube"],
    "excludes": ["cosplay"],
}
def main() -> int:
    log("=== LIVE END-TO-END (real servers, real data) ===\n")

    log("--- web pages ---")
    for page in ("/", "/login", "/radars", "/radars/new", "/saved", "/settings", "/profile"):
        check_web(page)

    log("\n--- api: taxonomy ---")
    status, health = call("GET", f"{API}/health")
    log(f"GET  /health        -> {status} {health}")

    status, countries = call("GET", f"{API}/countries?supported_only=true")
    count = len(countries) if isinstance(countries, list) else "?"
    log(f"GET  /countries     -> {status} supported={count}")

    status, sources = call("GET", f"{API}/sources")
    if isinstance(sources, list):
        for source in sources:
            log(
                f"     {source['status']:<22} {source['id']:<20} "
                f"records={source['total_records']}"
            )

    log("\n--- api: sign up ---")
    email = f"live{uuid.uuid4().hex[:8]}@radar.example.com"
    status, result = call(
        "POST", f"{API}/auth/register", {"email": email, "password": "supersecret1"}
    )
    if status != 201:
        log(f"POST /register     -> FAILED {status} {result}")
        return 1
    token = result["access_token"]
    log(f"POST /register     -> {status} {email}")

    log("\n--- api: create radar with AND / OR / EXCLUDE ---")
    status, radar = call("POST", f"{API}/radars", RADAR_BODY, token)
    name = radar.get("name") if isinstance(radar, dict) else radar
    log(f"POST /radars       -> {status} {name}")
    radar_id = radar.get("id") if isinstance(radar, dict) else None

    status, ast = call("GET", f"{API}/radars/{radar_id}/conditions", None, token)
    op = ast.get("ast", {}).get("op") if isinstance(ast, dict) else "?"
    kids = len(ast.get("ast", {}).get("children", [])) if isinstance(ast, dict) else 0
    log(f"GET  /conditions   -> {status} ast_op={op} children={kids}")

    log("\n--- api: signals ---")
    status, page = call("GET", f"{API}/signals?limit=5", None, token)
    items = page.get("items", []) if isinstance(page, dict) else []
    total = page.get("total") if isinstance(page, dict) else "?"
    log(f"GET  /signals      -> {status} total={total}")
    for signal in items[:4]:
        log(
            f"     [{signal['status']:<8}] {signal['title'][:42]} "
            f"str={signal['strength']} growth={signal['growth']} "
            f"{signal['country_code']} {signal['source_id']}"
        )

    if items:
        sid = items[0]["id"]
        status, detail = call("GET", f"{API}/signals/{sid}", None, token)
        snaps = len(detail.get("snapshots", [])) if isinstance(detail, dict) else 0
        log(f"GET  /signal/{sid[:8]} -> {status} snapshots={snaps}")

        status, hist = call("GET", f"{API}/signals/{sid}/history", None, token)
        points = len(hist.get("points", [])) if isinstance(hist, dict) else 0
        log(f"GET  /history      -> {status} points={points}")

        status, saved = call("POST", f"{API}/signals/{sid}/save", {}, token)
        flag = saved.get("is_saved") if isinstance(saved, dict) else saved
        log(f"POST /save         -> {status} is_saved={flag}")

        status, listing = call("GET", f"{API}/saved", None, token)
        log(f"GET  /saved        -> {status} count={len(listing) if isinstance(listing, list) else '?'}")

        status, _ = call("DELETE", f"{API}/signals/{sid}/save", None, token)
        log(f"DEL  /save         -> {status}")

    log("\n--- api: custom tag ---")
    status, tag = call("POST", f"{API}/custom-tags", CUSTOM_TAG_BODY, token)
    slug = tag.get("slug") if isinstance(tag, dict) else tag
    log(f"POST /custom-tag   -> {status} slug={slug}")

    log("\n--- api: source health ---")
    status, report = call("GET", f"{API}/system/source-health")
    if isinstance(report, dict):
        log(f"GET  /source-health -> {status} {report.get('summary')}")

    log("\n=== LIVE CHECK COMPLETE ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())