"""Database seeding: countries, tags, sources. Idempotent."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Country, Source, Tag, TagAlias
from app.models.enums import SourceStatus
from app.pipeline.collectors import all_adapters
from app.pipeline.normalization.normalizer import normalize_text
from app.seed.countries import COUNTRIES, flag_emoji, slugify_country
from app.seed.tag_taxonomy import TAXONOMY

logger = get_logger(__name__)


async def seed_countries(session: AsyncSession) -> int:
    existing = {c.code for c in (await session.scalars(select(Country))).all()}
    added = 0
    for code, alpha3, name, region, supported in COUNTRIES:
        if code in existing:
            continue
        session.add(
            Country(
                code=code,
                alpha3=alpha3,
                name=name,
                slug=slugify_country(name),
                flag=flag_emoji(code),
                region=region,
                is_supported=supported,
            )
        )
        added += 1
    if added:
        await session.commit()
    logger.info("countries seeded: +%d", added)
    return added


async def seed_tags(session: AsyncSession) -> int:
    existing = {t.slug for t in (await session.scalars(select(Tag))).all()}
    added = 0
    for category, entries in TAXONOMY.items():
        for slug, name, emoji in entries:
            if slug in existing:
                continue
            session.add(
                Tag(
                    slug=slug,
                    name=name,
                    category=category,
                    emoji=emoji,
                    is_system=True,
                    description=f"{name} signals in the {category} category",
                )
            )
            added += 1

    # aliases: multi-word phrases from the taxonomy
    from app.seed.tag_taxonomy import TAG_ALIASES

    tags = {t.slug: t for t in (await session.scalars(select(Tag))).all()}
    existing_aliases = {
        (a.normalized, a.tag_id)
        for a in (await session.scalars(select(TagAlias))).all()
    }

    for slug, phrases in TAG_ALIASES.items():
        tag = tags.get(slug)
        if tag is None:
            continue
        for phrase in dict.fromkeys(phrases):
            clean = normalize_text(phrase)
            if not clean or clean == normalize_text(tag.name):
                continue
            if (clean, tag.id) in existing_aliases:
                continue
            existing_aliases.add((clean, tag.id))
            session.add(
                TagAlias(tag_id=tag.id, alias=phrase, normalized=clean)
            )
            added += 1

    if added:
        await session.commit()
    logger.info("tags seeded: +%d", added)
    return added


async def seed_sources(session: AsyncSession) -> int:
    """Mirror the runtime registry into the sources table."""
    existing = {s.id: s for s in (await session.scalars(select(Source))).all()}
    added = 0
    updated = 0

    for adapter in all_adapters():
        needs_credentials = adapter.credentials_required
        current = existing.get(adapter.source_id)

        if current is None:
            session.add(
                Source(
                    id=adapter.source_id,
                    name=adapter.name,
                    type=adapter.type,
                    adapter=adapter.adapter_name,
                    description=adapter.description,
                    enabled=True,
                    status=(
                        SourceStatus.OPTIONAL_CREDENTIALS
                        if needs_credentials
                        else SourceStatus.ACTIVE
                    ),
                    status_reason=adapter.credentials_hint,
                    cost=adapter.cost,
                    credentials_required=needs_credentials,
                    capabilities=adapter.capabilities,
                    priority=adapter.priority,
                    collect_interval_seconds=adapter.collect_interval_seconds,
                )
            )
            added += 1
            continue

        current.name = adapter.name
        current.type = adapter.type
        current.adapter = adapter.adapter_name
        current.description = adapter.description
        current.capabilities = adapter.capabilities
        current.priority = adapter.priority
        current.collect_interval_seconds = adapter.collect_interval_seconds
        current.credentials_required = needs_credentials
        current.status_reason = adapter.credentials_hint
        updated += 1

    if added or updated:
        await session.commit()
    logger.info("sources synced: +%d, ~%d", added, updated)
    return added