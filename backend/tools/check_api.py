"""Verify the FastAPI app serves every route end to end."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import httpx

from app.db.session import engine, init_models
from app.main import app

LINES: list[str] = []

RADAR_BODY = {
    "name": "Korea Makeup",
    "emoji": "🇰🇷",
    "conditions": {
        "op": "AND",
        "children": [
            {
                "op": "OR",
                "children": [
                    {"type": "country", "operator": "IN", "value": ["KR", "JP"]}
                ],
            },
            {
                "op": "OR",
                "children": [
                    {
                        "type": "source",
                        "operator": "IN",
                        "value": ["tiktok", "youtube", "google_trends"],
                    }
                ],
            },
            {
                "op": "NOT",
                "children": [
                    {"type": "tag", "operator": "IN", "value": ["cosplay"]}
                ],
            },
        ],
    },
    "notification_frequency": "INSTANT",
}


def log(message: str) -> None:
    LINES.append(message)
    Path("api_report.txt").write_text("\n".join(LINES), encoding="utf-8")


async def check_public(client: httpx.AsyncClient) -> None:
    log(f"GET /              -> {(await client.get('/')).status_code}")

    health = await client.get("/api/v1/health")
    log(f"GET /health        -> {health.status_code} {health.json()}")

    countries = await client.get("/api/v1/countries")
    log(f"GET /countries     -> {countries.status_code} total={len(countries.json())}")

    supported = await client.get("/api/v1/countries?supported_only=true")
    log(f"    supported      -> {len(supported.json())}")

    registry = await client.get("/api/v1/sources/registry")
    log(f"GET /registry      -> {registry.status_code} adapters={len(registry.json())}")

    tags = await client.get("/api/v1/tags")
    log(f"GET /tags          -> {tags.status_code} count={len(tags.json())}")

    categories = await client.get("/api/v1/tags/categories")
    log(
        "GET /categories    -> "
        + ", ".join(f"{c['category']}:{c['count']}" for c in categories.json())
    )

    ctypes = await client.get("/api/v1/condition-types")
    log(f"GET /cond-types    -> {ctypes.status_code} types={len(ctypes.json())}")

    detail = await client.get("/api/v1/system/source-health")
    log(f"GET /source-health -> {detail.status_code} {detail.json()['summary']}")

    for src in (await client.get("/api/v1/sources")).json():
        log(f"    {src['status']:<22} {src['id']:<20} records={src['total_records']}")
async def check_signals(client: httpx.AsyncClient, headers: dict) -> None:
    signals = await client.get("/api/v1/signals?limit=5", headers=headers)
    data = signals.json()
    log(f"GET /signals       -> {signals.status_code} total={data['total']}")
    if not data["items"]:
        log("    (no signals yet - run tools.e2e_check first)")
        return

    first = data["items"][0]
    sid = first["id"]
    log(
        f"    [{first['status']}] {first['title'][:46]} "
        f"str={first['strength']} growth={first['growth']} "
        f"country={first['country_code']} src={first['source_id']}"
    )

    detail = await client.get(f"/api/v1/signals/{sid}", headers=headers)
    log(
        f"GET /signals/id    -> {detail.status_code} "
        f"snapshots={len(detail.json()['snapshots'])}"
    )

    history = await client.get(f"/api/v1/signals/{sid}/history", headers=headers)
    log(
        f"GET /history       -> {history.status_code} "
        f"points={len(history.json()['points'])}"
    )

    save = await client.post(f"/api/v1/signals/{sid}/save", headers=headers)
    log(f"POST /save         -> {save.status_code} is_saved={save.json()['is_saved']}")

    saved = await client.get("/api/v1/saved", headers=headers)
    log(f"GET /saved         -> {saved.status_code} count={len(saved.json())}")

    mute = await client.post(f"/api/v1/signals/{sid}/mute", headers=headers)
    log(f"POST /mute         -> {mute.status_code} is_ignored={mute.json()['is_ignored']}")

    unmute = await client.delete(f"/api/v1/signals/{sid}/mute", headers=headers)
    log(f"DEL /mute          -> {unmute.status_code}")

    unsave = await client.delete(f"/api/v1/signals/{sid}/save", headers=headers)
    log(f"DEL /save          -> {unsave.status_code}")


async def check_extras(client: httpx.AsyncClient, headers: dict) -> None:
    ct = await client.post(
        "/api/v1/custom-tags",
        headers=headers,
        json={
            "name": "Korean Makeup",
            "keywords": ["korean makeup", "k-beauty", "glass skin"],
            "hashtags": ["kbeauty", "glassskin"],
            "country_codes": ["KR"],
            "source_ids": ["tiktok", "youtube"],
            "excludes": ["cosplay"],
        },
    )
    log(f"POST /custom-tag   -> {ct.status_code} slug={ct.json().get('slug')}")

    ct_list = await client.get("/api/v1/custom-tags", headers=headers)
    log(f"GET /custom-tags   -> {ct_list.status_code} count={len(ct_list.json())}")

    key = await client.get("/api/v1/notifications/push/public-key")
    log(f"GET /vapid         -> {key.status_code}")

    deliveries = await client.get(
        "/api/v1/notifications/deliveries", headers=headers
    )
    log(f"GET /deliveries    -> {deliveries.status_code} count={len(deliveries.json())}")

    docs = await client.get("/openapi.json")
    log(f"GET /openapi.json  -> {docs.status_code} routes={len(docs.json().get('paths', {}))}")
async def main() -> int:
    await init_models()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=180
    ) as client:
        await check_public(client)

        email = f"t{uuid.uuid4().hex[:8]}@radar.example.com"
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "supersecret1"},
        )
        log(f"POST /register     -> {reg.status_code} {str(reg.json())[:120]}")
        if reg.status_code != 201:
            raise RuntimeError(f"register failed: {reg.status_code} {reg.text[:300]}")
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        me = await client.get("/api/v1/auth/me", headers=headers)
        log(f"GET /me            -> {me.status_code} {me.json()['email']}")

        radar = await client.post("/api/v1/radars", headers=headers, json=RADAR_BODY)
        log(f"POST /radars       -> {radar.status_code} {radar.json().get('name')}")
        radar_id = radar.json().get("id")

        listing = await client.get("/api/v1/radars", headers=headers)
        log(f"GET /radars        -> {listing.status_code} count={len(listing.json())}")

        conds = await client.get(
            f"/api/v1/radars/{radar_id}/conditions", headers=headers
        )
        log(f"GET /conditions    -> {conds.status_code} ast={'ast' in conds.json()}")

        preview = await client.post(
            "/api/v1/radars/preview",
            headers=headers,
            json={
                "conditions": {
                    "op": "AND",
                    "children": [
                        {"type": "growth", "operator": "GT", "value": 0}
                    ],
                }
            },
        )
        log(f"POST /preview      -> {preview.status_code} matched={preview.json()['matched']}")

        run = await client.post(f"/api/v1/radars/{radar_id}/run", headers=headers)
        log(f"POST /radars/run   -> {run.status_code} {run.json()}")

        await check_signals(client, headers)
        await check_extras(client, headers)

    await engine.dispose()
    Path("api_report.txt").write_text("\n".join(LINES), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))