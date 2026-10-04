"""Verifies every endpoint added in the product-UX phase over real HTTP.

Runs against the live app with TestClient so no server process is needed, and
prints an honest PASS/FAIL table.
"""

import asyncio
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


async def seed(client: TestClient) -> tuple[str, str]:
    """Make sure there is at least one user, radar and signal to test with."""
    from app.db.session import SessionLocal
    from app.models import Signal, User
    from sqlalchemy import select

    async with SessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        signals = (
            (await session.execute(select(Signal).limit(5)))
            .scalars()
            .unique()
            .all()
        )
        if not users:
            print("no seeded user or signal — run tools.e2e_check first")
            raise SystemExit(2)
        return users[0].id, signals[0].id if signals else ""


def main() -> int:
    with TestClient(app) as client:
        signal_id = asyncio.run(seed(client))[1]

        # ---- public reading (no token) -------------------------------
        r = client.get("/api/v1/signals")
        check("GET /signals is public", r.status_code == 200, f"status={r.status_code}")
        body = r.json() if r.status_code == 200 else {}
        check(
            "public feed returns items",
            isinstance(body.get("items"), list) and len(body["items"]) > 0,
            f"items={len(body.get('items', []))} total={body.get('total')}",
        )

        r = client.get("/api/v1/stats")
        stats = r.json() if r.status_code == 200 else {}
        check(
            "GET /stats is public",
            r.status_code == 200 and stats.get("total_signals", 0) > 0,
            f"total={stats.get('total_signals')} sources={stats.get('sources')}",
        )

        r = client.get("/api/v1/discover?limit=10")
        disc = r.json() if r.status_code == 200 else {}
        check(
            "GET /discover is public",
            r.status_code == 200 and "items" in disc,
            f"items={len(disc.get('items', []))}",
        )

        if signal_id:
            r = client.get(f"/api/v1/signals/{signal_id}")
            check(
                "GET /signals/{id} is public",
                r.status_code == 200,
                f"status={r.status_code}",
            )

            r = client.get(f"/api/v1/signals/{signal_id}/related")
            check(
                "GET /signals/{id}/related is public",
                r.status_code == 200 and isinstance(r.json(), list),
                f"related={len(r.json()) if r.status_code == 200 else 'n/a'}",
            )

            r = client.get(f"/api/v1/signals/{signal_id}/history")
            check(
                "GET /signals/{id}/history is public",
                r.status_code == 200,
                f"status={r.status_code}",
            )

        # ---- auth still required where it must be -------------------
        for method, path in (
            ("post", "/api/v1/radars"),
            ("post", "/api/v1/custom-tags"),
            ("post", "/api/v1/notifications/push/subscribe"),
            ("post", f"/api/v1/signals/{signal_id}/save"),
        ):
            r = getattr(client, method)(path, json={})
            check(
                f"{method.upper()} {path} requires auth",
                r.status_code == 401,
                f"status={r.status_code}",
            )

        r = client.get("/api/v1/radars")
        check(
            "GET /radars requires auth",
            r.status_code == 401,
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