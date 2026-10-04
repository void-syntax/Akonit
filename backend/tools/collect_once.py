"""One collection cycle, then exit.

Designed for cron-based schedulers (GitHub Actions) where a long-running
process is impossible. Prints a machine-readable summary and exits non-zero only
if nothing at all could be collected.
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
from app.services.pipeline_service import (  # noqa: E402
    refresh_signal_metrics,
    run_collection_cycle,
)
from app.workers.tasks import active_countries  # noqa: E402


async def main() -> int:
    async with SessionLocal() as session:
        countries = await active_countries(session)
        stats = await run_collection_cycle(
            session,
            countries=countries,
            limit_per_source=40,
        )
        refreshed = await refresh_signal_metrics(session)

    summary = {
        "countries": countries,
        "fetched": stats.fetched,
        "signals_created": stats.signals_created,
        "signals_updated": stats.signals_updated,
        "sources_ok": stats.sources_ok,
        "sources_failed": stats.sources_failed,
        "metrics_refreshed": refreshed,
        "errors": stats.errors,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    with_summary = Path("collection_summary.json")
    with_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # A run where nothing was fetched at all is a genuine failure worth
    # surfacing, even when individual sources are degraded.
    return 0 if stats.fetched > 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))