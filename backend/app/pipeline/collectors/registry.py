"""Source Registry.

Adapters self-register via @register_source, so adding a new collector is a
single new file with no changes anywhere else.
"""

from __future__ import annotations

import asyncio
from typing import TypeVar

from app.core.config import settings
from app.core.logging import get_logger
from app.pipeline.collectors.base import FetchContext, FetchResult, SourceAdapter
from app.pipeline.collectors.http_client import HttpClient

logger = get_logger("collector.registry")

_REGISTRY: dict[str, SourceAdapter] = {}
_SOURCE_COOLDOWNS: dict[str, float] = {}

A = TypeVar("A", bound=SourceAdapter)


def register_source(cls: type[A]) -> type[A]:
    """Class decorator: instantiate and store the adapter."""
    adapter = cls()
    if adapter.source_id in _REGISTRY:
        logger.debug("skipping duplicate source id: %s", adapter.source_id)
        return cls
    _REGISTRY[adapter.source_id] = adapter
    logger.debug("registered source %s (%s)", adapter.source_id, adapter.adapter_name)
    return cls


def get_adapter(source_id: str) -> SourceAdapter | None:
    return _REGISTRY.get(source_id)


def all_adapters() -> list[SourceAdapter]:
    return sorted(_REGISTRY.values(), key=lambda a: (a.priority, a.source_id))


def source_is_cooling_down(source_id: str) -> bool:
    """Avoid repeating known failures on every scheduler tick."""
    until = _SOURCE_COOLDOWNS.get(source_id, 0.0)
    if asyncio.get_running_loop().time() < until:
        return True
    _SOURCE_COOLDOWNS.pop(source_id, None)
    return False


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


def _is_missing_credentials(error: str) -> bool:
    text = error.lower()
    return any(
        phrase in text
        for phrase in (
            "not configured",
            "no instagram graph api token",
            "no tiktok app token",
            "no x api bearer token",
            "reddit oauth credentials are not configured",
        )
    )


async def run_strategy_cascade(
    adapter: SourceAdapter, ctx: FetchContext, client: HttpClient
) -> FetchResult:
    """Try each strategy in order; first success wins, failures are recorded."""
    from app.pipeline.collectors.base import SourceUnavailable
    from app.pipeline.resilience import get_circuit_breaker, get_rate_limiter

    cb = get_circuit_breaker(adapter.source_id)
    rl = get_rate_limiter(adapter.source_id)

    if cb.is_open():
        logger.info(
            "[%s] circuit is OPEN; source temporarily skipped.", adapter.source_id
        )
        return FetchResult(
            source_id=adapter.source_id,
            events=[],
            strategy="none",
            ok=True,
            notes="circuit breaker open",
        )

    if source_is_cooling_down(adapter.source_id):
        return FetchResult(
            source_id=adapter.source_id,
            events=[],
            strategy="none",
            ok=True,
            notes="source cooldown after failure",
        )

    if not await rl.async_acquire():
        logger.warning(
            "[%s] rate limit exceeded. Returning empty list gracefully.",
            adapter.source_id,
        )
        return FetchResult(
            source_id=adapter.source_id,
            events=[],
            strategy="none",
            ok=True,
            notes="rate limit exceeded",
        )

    errors: list[str] = []
    strategy_succeeded = False
    last_failure: str | None = None
    for strategy in adapter.strategies:
        try:
            events = await strategy.fetch(client, ctx)
        except SourceUnavailable as exc:
            errors.append(f"{strategy.name}: {exc}")
            last_failure = str(exc)
            logger.info(
                "[%s] strategy %s unavailable: %s",
                adapter.source_id,
                strategy.name,
                exc,
            )
            continue
        except Exception as exc:  # unexpected: treat as strategy failure
            errors.append(f"{strategy.name}: unexpected {exc!r}")
            last_failure = repr(exc)
            logger.warning(
                "[%s] strategy %s crashed: %r", adapter.source_id, strategy.name, exc
            )
            continue

        if not events:
            # An empty response is a valid result only when there is no more
            # informative fallback. Continue the cascade so a primary API that
            # has no matching items cannot hide public fallback data.
            errors.append(f"{strategy.name}: returned no events")
            last_failure = "returned no events"
            continue

        strategy_succeeded = True
        cb.record_success()
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

    if not strategy_succeeded:
        if last_failure == "returned no events":
            if not errors or all("returned no events" in error for error in errors):
                # Every strategy answered but none had new items.
                cb.record_success()
                return FetchResult(
                    source_id=adapter.source_id,
                    events=[],
                    strategy="none",
                    ok=True,
                    notes="no new events",
                )
        if errors and all(_is_missing_credentials(error) for error in errors):
            # A missing optional credential is a configuration state, not a
            # provider outage. Avoid tripping its circuit breaker/cooldown.
            _mark_optional_credentials(adapter)
            return FetchResult(
                source_id=adapter.source_id,
                events=[],
                strategy="none",
                ok=False,
                error=" | ".join(errors),
            )
        cb.record_failure()
        if last_failure not in {"returned no events", None}:
            cooldown = max(settings.source_cooldown_seconds, 0)
            _SOURCE_COOLDOWNS[adapter.source_id] = (
                asyncio.get_running_loop().time() + cooldown
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
        a for a in all_adapters() if source_ids is None or a.source_id in source_ids
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
