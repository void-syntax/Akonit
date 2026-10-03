"""Real-data probe: runs every registered collector and prints what came back.

Usage:  python -m tools.probe_sources [--only tiktok,youtube] [--limit 20]
This is the verification tool for the zero-manual-setup requirement.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.collectors import collect_all  # noqa: E402
from app.pipeline.collectors.base import FetchContext  # noqa: E402
from app.pipeline.collectors.registry import all_adapters  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--countries", default="US,GB,KR,JP,TR,AE,AZ")
    args = parser.parse_args()

    ctx = FetchContext(
        countries=[c.strip().upper() for c in args.countries.split(",") if c.strip()],
        limit=args.limit,
    )
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    print(f"Registered sources: {len(all_adapters())}")
    print("=" * 78)

    started = time.monotonic()
    results = await collect_all(ctx, list(only) or None)
    elapsed = time.monotonic() - started

    ok = 0
    for result in sorted(results, key=lambda r: r.source_id):
        if result.ok and result.events:
            ok += 1
            sample = result.events[0]
            print(f"[OK]   {result.source_id:<20} {len(result.events):>4} events"
                  f"  via {result.strategy:<22} {elapsed:>5.1f}s total")
            print(f"       e.g. {sample.title[:70]!r}")
            print(f"       activity={sample.activity:,.0f} ({sample.activity_metric})"
                  f"  country={sample.country_code}  rank={sample.rank}")
            print(f"       url={sample.url[:90]}")
        else:
            print(f"[FAIL] {result.source_id:<20} {result.error}")
            if result.notes:
                print(f"       notes: {result.notes[:200]}")
    print("=" * 78)
    print(f"Working: {ok}/{len(results)}  elapsed={elapsed:.1f}s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))