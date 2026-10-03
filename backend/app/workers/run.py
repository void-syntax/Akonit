"""Entry point for the background worker container."""

from __future__ import annotations

import asyncio

from app.workers.schedule import main

if __name__ == "__main__":
    asyncio.run(main())