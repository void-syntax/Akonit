"""Collector layer.

Every source implements its own adapter. Adapters return RawEvent objects and
never touch the database or detection logic — that keeps layers independent.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.models.enums import SourceType


@dataclass
class RawEvent:
    """One observed item from a source, before normalization."""

    source_id: str
    external_id: str
    title: str
    url: str
    description: str = ""
    activity: float = 0.0
    activity_metric: str = "unknown"
    country_code: str | None = None
    rank: int | None = None
    hashtags: list[str] = field(default_factory=list)
    thumbnail: str | None = None
    category: str | None = None
    published_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Collection time must remain distinct from publication time. Using the
    # publish timestamp as `observed_at` made an old-but-reseen item look
    # invisible to recency, retention and cross-source deduplication.
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FetchResult:
    """What a single fetch attempt produced (possibly via a fallback strategy)."""

    source_id: str
    events: list[RawEvent]
    strategy: str
    ok: bool = True
    error: str | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset_at: datetime | None = None
    notes: str | None = None

    def __len__(self) -> int:
        return len(self.events)


class SourceUnavailable(RuntimeError):
    """Raised by a strategy when it cannot produce data."""

    def __init__(self, message: str, *, rate_limit_reset_at: datetime | None = None):
        super().__init__(message)
        self.rate_limit_reset_at = rate_limit_reset_at


class Strategy(abc.ABC):
    """A credential cascade step. The runner tries strategies in order."""

    name: str = "base"

    @abc.abstractmethod
    async def fetch(self, client: Any, ctx: "FetchContext") -> list[RawEvent]:
        """Return events or raise SourceUnavailable."""


class FetchContext:
    """Per-run options: countries, keywords, limits."""

    def __init__(
        self,
        countries: list[str] | None = None,
        keywords: list[str] | None = None,
        limit: int = 50,
        extra: dict[str, Any] | None = None,
    ):
        self.countries = countries or []
        self.keywords = keywords or []
        self.limit = limit
        self.extra = extra or {}

    def for_country(self, country: str) -> "FetchContext":
        return FetchContext([country], self.keywords, self.limit, self.extra)


class SourceAdapter(abc.ABC):
    """Base adapter. Subclass + decorate with @register_source."""

    source_id: str = ""
    name: str = ""
    type: SourceType = SourceType.SOCIAL
    description: str = ""
    capabilities: list[str] = []
    priority: int = 100
    collect_interval_seconds: int = 900
    cost: str = "FREE"
    credentials_required: bool = False
    credentials_hint: str | None = None
    strategies: list[Strategy] = []
    health_note_value: str | None = None

    @property
    def adapter_name(self) -> str:
        return f"{type(self).__module__.rsplit('.', 1)[-1]}.{type(self).__name__}"

    @abc.abstractmethod
    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        """Run the credential cascade and return the first successful result."""

    def health_note(self) -> str | None:
        return self.health_note_value
