"""Source Registry.

Adapters self-register via @register_source, so adding a new collector is a
single new file with no changes anywhere else.
"""

from __future__ import annotations

import asyncio
from typing import TypeVar

from app.core.logging import get_logger
from app.pipeline.collectors.base import FetchContext, FetchResult, SourceAdapter
from app.pipeline.collectors.http_client import HttpClient

logger = get_logger("collector.registry")

_REGISTRY: dict[str, SourceAdapter] = {}

A = TypeVar("A", bound=SourceAdapter)


def register_source(cls: type[A]) -> type[A]:
    """Class decorator: instantiate and store the adapter."""
    adapter = cls()
    if adapter.source_id in _REGISTRY:
        raise ValueError(f"duplicate source id: {adapter.source_id}")
    _REGISTRY[adapter.source_id] = adapter
    logger.debug("registered source %s (%s)", adapter.source_id, adapter.adapter_name)
    return cls


def get_adapter(source_id: str) -> SourceAdapter | None:
    return _REGISTRY.get(source_id)


def all_adapters() -> list[SourceAdapter]:
    return sorted(_REGISTRY.values(), key=lambda a: (a.priority, a.source_id))


def registry_snapshot() -> list[dict]:
    return [
        {
            "id": a.source_id,
            "name": a.name,
            "type": a.type.value,
            "adapter": a.adapter_name,
            "description": a.description,
            "priority": a.priority,
            "cost": a.cost,
            "credentials_required": a.credentials_required,
            "credentials_hint": a.credentials_hint,
            "capabilities": a.capabilities,
            "collect_interval_seconds": a.collect_interval_seconds,
            "strategies": [s.name for s in a.strategies],
        }
        for a in all_adapters()
    ]


def _mark_optional_credentials(adapter: SourceAdapter) -> None:
    adapter.health_note_value = (
        adapter.credentials_hint
        or "Adapter implemented and tested; requires official credentials to run."
    )


async def run_strategy_cascade(
    adapter: SourceAdapter, ctx: FetchContext, client: HttpClient
) -> FetchResult:
    """Try each strategy in order; first success wins, failures are recorded."""
    from app.pipeline.collectors.base import SourceUnavailable

    errors: list[str] = []
    for strategy in adapter.strategies:
        try:
            events = await strategy.fetch(client, ctx)
        except SourceUnavailable as exc:
            errors.append(f"{strategy.name}: {exc}")
            logger.info("[%s] strategy %s unavailable: %s", adapter.source_id, strategy.name, exc)
            continue
        except Exception as exc:  # unexpected: treat as strategy failure
            errors.append(f"{strategy.name}: unexpected {exc!r}")
            logger.warning("[%s] strategy %s crashed: %r", adapter.source_id, strategy.name, exc)
            continue

        if not events:
            errors.append(f"{strategy.name}: returned no events")
            continue

        logger.info(
            "[%s] %s fetched %d events", adapter.source_id, strategy.name, len(events)
        )
        return FetchResult(
            source_id=adapter.source_id,
            events=events,
            strategy=strategy.name,
            ok=True,
            notes="; ".join(errors) if errors else None,
        )

    return FetchResult(
        source_id=adapter.source_id,
        events=[],
        strategy="none",
        ok=False,
        error=" | ".join(errors) or "no strategies configured",
    )


async def collect_all(
    ctx: FetchContext, source_ids: list[str] | None = None
) -> list[FetchResult]:
    """Run every (or the selected) adapter concurrently; failures are isolated."""
    adapters = [
        a
        for a in all_adapters()
        if source_ids is None or a.source_id in source_ids
    ]
    client = HttpClient()
    try:
        tasks = [run_strategy_cascade(a, ctx, client) for a in adapters]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await client.aclose()

    out: list[FetchResult] = []
    for adapter, result in zip(adapters, results, strict=True):
        if isinstance(result, BaseException):
            out.append(
                FetchResult(
                    source_id=adapter.source_id,
                    events=[],
                    strategy="none",
                    ok=False,
                    error=f"runner crashed: {result!r}",
                )
            )
        else:
            out.append(result)
    return out