"""Match signals against radars and deliver notifications, then exit.

Companion to collect_once for cron schedulers: queues everything due under each
radar's frequency and pushes it through Telegram / web push.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.notifications.dispatcher import flush_deliveries, notify_matches  # noqa: E402
from app.services.radar_service import match_batch  # noqa: E402


async def main() -> int:
    async with SessionLocal() as session:
        outcomes = await match_batch(session, lookback_minutes=180)
        queued = await notify_matches(
            session, signal_ids=[o.signal_id for o in outcomes]
        )
        # Queue anything else that became due since the last tick.
        queued += await notify_matches(session)
        delivered = await flush_deliveries(session)

    summary = {
        "matched": len(outcomes),
        "queued": queued,
        "delivered": delivered,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    Path("notify_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Notification problems must not fail the whole cycle: data was collected
    # and matched, the delivery layer can retry on the next run.
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))