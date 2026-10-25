"""Adapters package for additional collectors."""

from __future__ import annotations

from app.pipeline.collectors.adapters import rss_news  # noqa: F401
from app.pipeline.collectors.adapters import reddit  # noqa: F401
from app.pipeline.collectors.adapters import arxiv  # noqa: F401
from app.pipeline.collectors.adapters import sec_edgar  # noqa: F401
from app.pipeline.collectors.adapters import uspto_patents  # noqa: F401
from app.pipeline.collectors.adapters import trademarks  # noqa: F401
from app.pipeline.collectors.adapters import huggingface  # noqa: F401
from app.pipeline.collectors.adapters import polymarket  # noqa: F401
from app.pipeline.collectors.adapters import arxiv_trending  # noqa: F401
from app.pipeline.collectors.adapters import bluesky_jetstream  # noqa: F401
