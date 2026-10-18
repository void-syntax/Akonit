"""Importing this module registers every source adapter with the registry.

Adding a new collector is a single new file plus one import line below.
"""

from app.pipeline.collectors import ai_tech  # noqa: F401
from app.pipeline.collectors.adapters import rss_news  # noqa: F401
from app.pipeline.collectors import devto  # noqa: F401
from app.pipeline.collectors import google_news_trends  # noqa: F401
from app.pipeline.collectors import google_trends  # noqa: F401
from app.pipeline.collectors import hackernews  # noqa: F401
from app.pipeline.collectors import instagram  # noqa: F401
from app.pipeline.collectors import lobsters  # noqa: F401
from app.pipeline.collectors import npm  # noqa: F401
from app.pipeline.collectors import producthunt  # noqa: F401
from app.pipeline.collectors import reddit  # noqa: F401
from app.pipeline.collectors import stackoverflow  # noqa: F401
from app.pipeline.collectors import tiktok  # noqa: F401
from app.pipeline.collectors import x_trends  # noqa: F401
from app.pipeline.collectors import youtube  # noqa: F401
from app.pipeline.collectors.registry import (
    all_adapters,
    collect_all,
    get_adapter,
    register_source,
    registry_snapshot,
    run_strategy_cascade,
)

__all__ = [
    "all_adapters",
    "collect_all",
    "get_adapter",
    "register_source",
    "registry_snapshot",
    "run_strategy_cascade",
]