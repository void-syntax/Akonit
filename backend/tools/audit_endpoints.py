"""Functional audit: exercise every route the UI depends on.

The frontend audit turned up plenty of buttons wired to nothing, so this walks
the same paths a user would: browse, filter, save, build a radar, match, delete.
It runs entirely offline against a throwaway database.

    python -m tools.audit_endpoints

Exits non-zero when any endpoint fails, so it can gate a release.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402


async def main() -> int:
    db = Path(tempfile.gettempdir()) / "audit_endpoints.db"
    if db.exists():
        db.unlink()
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    os.environ["REDIS_URL"] = ""

    from app.core.config import get_settings

    get_settings.cache_clear()

    # The engine is created when app.db.session is imported. Rebuild it after
    # setting the throwaway database URL so this audit never touches the user's DB.
    from app.db import session as db_session
    from app.core import database as db_core
    from sqlalchemy.ext.asyncio import async_sessionmaker

    await db_core.engine.dispose()
    db_core.database_url = os.environ["DATABASE_URL"]
    db_core.engine = db_core._build_engine(db_core.database_url)
    db_core.SessionLocal = async_sessionmaker(
        db_core.engine, expire_on_commit=False, class_=db_core.AsyncSession
    )
    db_session.engine = db_core.engine
    db_session.database_url = db_core.database_url
    db_session.SessionLocal = db_core.SessionLocal

    from app.db.session import SessionLocal, engine, init_models
    from app.main import app
    from app.models import Signal
    from app.models.enums import SignalStatus

    await init_models()
    await _seed(Signal, SignalStatus, SessionLocal)

    results: list[tuple[bool, str, int, str]] = []
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=60
    ) as client:
        radar_id = await _audit(client, results)

    await engine.dispose()

    for ok, name, code, body in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:22} {code}{'' if ok else f'  {body}'}")
    passed = sum(1 for r in results if r[0])
    print(f"\n{passed}/{len(results)} endpoints working")
    return 0 if passed == len(results) else 1


async def _seed(Signal, SignalStatus, SessionLocal) -> None:
    """One signal shaped like the card in the product description."""
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        session.add(
            Signal(
                id="sig1",
                cluster_id="sig1",
                title="Korean makeup technique is going viral",
                slug="korean-makeup-technique",
                description="A new style spreading across TikTok",
                hashtags=["makeup"],
                country_code="KR",
                country_name="South Korea",
                flag="\U0001F1F0\U0001F1F7",
                source_id="tiktok",
                source_url="https://www.tiktok.com/tag/makeup",
                first_seen_at=now - timedelta(minutes=18),
                last_seen_at=now,
                current_activity=50_000,
                previous_activity=13_000,
                growth=284.0,
                acceleration=40.0,
                status=SignalStatus.BREAKOUT,
                strength=87.0,
                age_minutes=18.0,
                activity_metric="views",
                keywords=["makeup", "beauty"],
            )
        )
        await session.commit()


async def _audit(client: httpx.AsyncClient, results: list) -> str | None:
    """Walk the read, save and radar paths a user actually takes."""

    async def check(name: str, method: str, path: str, body=None):
        kwargs = {"json": body} if body is not None else {}
        response = await getattr(client, method)(path, **kwargs)
        ok = response.status_code < 400
        results.append((ok, name, response.status_code, response.text[:70]))
        return response

    for name, path in [
        ("feed", "/api/v1/signals"),
        ("feed tab=breakout", "/api/v1/signals?tab=breakout"),
        ("feed tab=rising", "/api/v1/signals?tab=rising"),
        ("feed tab=new", "/api/v1/signals?tab=new"),
        ("feed filter tag", "/api/v1/signals?tag=makeup"),
        ("feed filter tags", "/api/v1/signals?tag=makeup&tag=beauty"),
        ("feed filter search", "/api/v1/signals?keyword=korean"),
        ("feed filter country", "/api/v1/signals?country=KR"),
        ("feed filter strength", "/api/v1/signals?min_strength=50"),
        ("signal detail", "/api/v1/signals/sig1"),
        ("signal history", "/api/v1/signals/sig1/history"),
        ("signal related", "/api/v1/signals/sig1/related"),
        ("discover", "/api/v1/discover"),
        (
            "discover multi-filter",
            "/api/v1/discover?country=KR&country=US&min_strength=50",
        ),
        ("discover by tag", "/api/v1/discover?tag=makeup&tag=beauty"),
        ("stats", "/api/v1/stats"),
        ("countries", "/api/v1/countries"),
        ("sources", "/api/v1/sources"),
        ("tags", "/api/v1/tags"),
        ("condition types", "/api/v1/condition-types"),
        ("source health", "/api/v1/system/source-health"),
        ("profile", "/api/v1/auth/profile"),
        ("custom tags", "/api/v1/custom-tags"),
        ("push public key", "/api/v1/notifications/push/public-key"),
        ("radars list", "/api/v1/radars"),
    ]:
        await check(name, "get", path)

    await check("SAVE signal", "post", "/api/v1/signals/sig1/save")
    await check("saved list", "get", "/api/v1/saved")
    await check("feed tab=saved", "get", "/api/v1/signals?tab=saved")
    await check("MUTE signal", "post", "/api/v1/signals/sig1/mute")
    await check("UNMUTE signal", "delete", "/api/v1/signals/sig1/mute")
    await check("UNSAVE signal", "delete", "/api/v1/signals/sig1/save")

    # The contract is the condition tree; countries, sources and tags are
    # derived from it, so the payload must express "Korea + TikTok + Makeup"
    # the way the radar builder does.
    korea_makeup = {
        "op": "AND",
        "children": [
            {"type": "COUNTRY", "operator": "IN", "value": ["KR"]},
            {"type": "SOURCE", "operator": "IN", "value": ["tiktok"]},
            {"type": "TAG", "operator": "IN", "value": ["makeup"]},
            {"type": "GROWTH", "operator": "GT", "value": 100},
        ],
    }
    created = await check(
        "CREATE radar",
        "post",
        "/api/v1/radars",
        {
            "name": "Korea Makeup",
            "emoji": "\U0001F48D",
            "conditions": korea_makeup,
            "signal_threshold": 50,
            "notification_frequency": "INSTANT",
            "notification_channels": [],
        },
    )
    if created.status_code >= 400:
        return None
    radar_id = created.json().get("id")

    await check("radar detail", "get", f"/api/v1/radars/{radar_id}")
    await check("radar summary", "get", f"/api/v1/radars/{radar_id}/summary")
    await check("radar conditions", "get", f"/api/v1/radars/{radar_id}/conditions")
    await check("radar run", "post", f"/api/v1/radars/{radar_id}/run")
    await check(
        "preview conditions",
        "post",
        "/api/v1/radars/preview",
        {
            "conditions": {
                "op": "AND",
                "children": [
                    {"type": "COUNTRY", "operator": "IN", "value": ["KR"]},
                    {"type": "TAG", "operator": "IN", "value": ["makeup"]},
                ],
            }
        },
    )
    await check("feed by radar", "get", f"/api/v1/signals?radar_id={radar_id}")
    await check(
        "UPDATE radar",
        "patch",
        f"/api/v1/radars/{radar_id}",
        {"name": "Korea Makeup v2"},
    )
    await check("DELETE radar", "delete", f"/api/v1/radars/{radar_id}")
    return radar_id


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
