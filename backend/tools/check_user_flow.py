"""Runs the signed-in user journey over real HTTP.

Registers a throwaway account, then exercises profile settings, custom tags
with all exclusion types, radar creation with a human-readable summary, and
notification channels. Every step prints an honest PASS/FAIL.
"""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, condition, detail))
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def auth_headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "flow@signalradar.dev",
            "password": "FlowTest123!",
            "display_name": "Flow Tester",
        },
    )
    if r.status_code not in (200, 201):
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "flow@signalradar.dev", "password": "FlowTest123!"},
        )
    if "access_token" not in r.json():
        raise SystemExit(
            f"auth failed: register/login returned {r.status_code} {r.text[:200]}"
        )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


CONDITIONS = {
    "op": "AND",
    "is_exclude": False,
    "children": [
        {"type": "COUNTRY", "operator": "IN", "value": ["KR", "JP"]},
        {
            "type": "SOURCE",
            "operator": "IN",
            "value": ["tiktok", "youtube", "google_trends"],
        },
        {"type": "TAG", "operator": "IN", "value": ["makeup"]},
        {"type": "GROWTH", "operator": "GT", "value": 100},
    ],
}

TAG_PAYLOAD = {
    "name": "Korea Makeup Flow",
    "keywords": ["kbeauty", "lipstick"],
    "aliases": ["korean cosmetics"],
    "hashtags": ["#kbeauty"],
    "country_codes": ["KR"],
    "source_ids": ["tiktok", "youtube"],
    "excludes": ["giveaway"],
    "exclude_hashtags": ["#ad"],
    "exclude_countries": ["US"],
    "emoji": "\U0001f484",
}


def main() -> int:
    with TestClient(app) as client:
        headers = auth_headers(client)

        r = client.get("/api/v1/auth/profile", headers=headers)
        profile = r.json()
        check(
            "GET /auth/profile exposes new settings fields",
            r.status_code == 200
            and all(
                key in profile
                for key in (
                    "signal_threshold",
                    "quiet_hours",
                    "theme",
                    "default_countries",
                    "default_sources",
                )
            ),
            f"threshold={profile.get('signal_threshold')} theme={profile.get('theme')}",
        )

        r = client.patch(
            "/api/v1/auth/profile",
            headers=headers,
            json={
                "signal_threshold": 42,
                "quiet_hours": {"start": "23:00", "end": "07:00", "enabled": True},
                "theme": "dark",
                "default_countries": ["KR", "JP"],
                "default_sources": ["tiktok", "youtube"],
            },
        )
        saved = r.json() if r.status_code == 200 else {}
        quiet = saved.get("quiet_hours") or {}
        check(
            "PATCH /auth/profile persists threshold + quiet hours",
            r.status_code == 200
            and saved.get("signal_threshold") == 42
            and quiet.get("enabled") is True
            and saved.get("default_countries") == ["KR", "JP"],
            f"threshold={saved.get('signal_threshold')} quiet={quiet}",
        )

        r = client.post("/api/v1/custom-tags", headers=headers, json=TAG_PAYLOAD)
        tag = r.json() if r.status_code in (200, 201) else {}
        check(
            "POST /custom-tags stores aliases + 3 exclusion types",
            tag.get("aliases") == ["korean cosmetics"]
            and tag.get("exclude_hashtags") == ["ad"]
            and tag.get("exclude_countries") == ["US"]
            and tag.get("excludes") == ["giveaway"],
            f"slug={tag.get('slug')}",
        )

        r = client.post(
            "/api/v1/custom-tags/preview", headers=headers, json=TAG_PAYLOAD
        )
        check(
            "POST /custom-tags/preview returns a match count",
            r.status_code == 200 and "matched" in r.json(),
            f"matched={r.json().get('matched') if r.status_code == 200 else 'n/a'}",
        )

        r = client.patch(
            f"/api/v1/custom-tags/{tag.get('id')}",
            headers=headers,
            json={**TAG_PAYLOAD, "name": "Korea Makeup Flow v2"},
        )
        check(
            "PATCH /custom-tags/{id} updates fields",
            r.status_code == 200 and r.json().get("name") == "Korea Makeup Flow v2",
            f"name={r.json().get('name') if r.status_code == 200 else 'n/a'}",
        )

        r = client.post(
            "/api/v1/radars",
            headers=headers,
            json={
                "name": "Korea Makeup",
                "emoji": "\U0001f1f0\U0001f1f7",
                "conditions": CONDITIONS,
                "signal_threshold": 30,
                "notification_frequency": "INSTANT",
                "notification_channels": ["WEB_PUSH"],
            },
        )
        radar = r.json() if r.status_code in (200, 201) else {}
        check(
            "POST /radars creates a radar",
            "id" in radar,
            f"id={radar.get('id')}",
        )

        r = client.get(f"/api/v1/radars/{radar.get('id')}/summary", headers=headers)
        parts = r.json().get("parts", []) if r.status_code == 200 else []
        check(
            "GET /radars/{id}/summary is human readable",
            any("South Korea" in p for p in parts)
            and any("TikTok" in p for p in parts)
            and any("Growth" in p for p in parts),
            f"parts={parts}",
        )

        r = client.post(
            "/api/v1/radars/preview", headers=headers, json={"conditions": CONDITIONS}
        )
        check(
            "POST /radars/preview counts matches",
            r.status_code == 200 and "matched" in r.json(),
            f"matched={r.json().get('matched') if r.status_code == 200 else 'n/a'}",
        )

        r = client.get("/api/v1/notifications/telegram/status", headers=headers)
        st = r.json() if r.status_code == 200 else {}
        check(
            "GET /notifications/telegram/status is honest",
            "bot_configured" in st and "push_configured" in st,
            f"bot={st.get('bot_configured')} push={st.get('push_configured')}",
        )

        endpoint = "https://push.example.com/sub/abc"
        r = client.post(
            "/api/v1/notifications/push/subscribe",
            headers=headers,
            json={"endpoint": endpoint, "keys": {"p256dh": "x", "auth": "y"}},
        )
        check(
            "POST /notifications/push/subscribe stores a subscription",
            r.status_code == 200 and r.json().get("subscriptions") == 1,
            f"subscriptions={r.json().get('subscriptions') if r.status_code == 200 else 'n/a'}",
        )

        r = client.request(
            "DELETE",
            "/api/v1/notifications/push/subscribe",
            headers=headers,
            json={"endpoint": endpoint},
        )
        check(
            "DELETE /notifications/push/subscribe removes it",
            r.status_code == 200 and r.json().get("subscriptions") == 0,
            f"subscriptions={r.json().get('subscriptions') if r.status_code == 200 else 'n/a'}",
        )

        r = client.delete(f"/api/v1/custom-tags/{tag.get('id')}", headers=headers)
        check(
            "DELETE /custom-tags/{id} works",
            r.status_code in (200, 204),
            f"status={r.status_code}",
        )

    failures = [name for name, ok, _ in RESULTS if not ok]
    print("=" * 60)
    print(f"{len(RESULTS) - len(failures)}/{len(RESULTS)} checks passed")
    if failures:
        print("failed:", ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())