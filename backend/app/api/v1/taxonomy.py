"""Countries, sources, tags and custom tags."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.models import Country, CustomTag, Source, Tag
from app.models.enums import ConditionOperator, ConditionType
from app.pipeline.normalization.normalizer import normalize_text, slugify
from app.schemas.api import (
    ConditionOption,
    CountryOut,
    CustomTagCreate,
    CustomTagOut,
    SourceOut,
    TagOut,
)

router = APIRouter(tags=["taxonomy"])


@router.get("/countries", response_model=list[CountryOut])
async def list_countries(
    session: SessionDep,
    q: str | None = Query(default=None, description="search by name"),
    supported_only: bool = False,
):
    statement = select(Country)
    if q:
        escaped_q = q.replace("%", r"\%").replace("_", r"\_")
        statement = statement.where(Country.name.ilike(f"%{escaped_q}%"))
    if supported_only:
        statement = statement.where(Country.is_supported.is_(True))
    return (
        (await session.execute(statement.order_by(Country.name)))
        .scalars()
        .all()
    )


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(session: SessionDep):
    return (
        (await session.execute(select(Source).order_by(Source.priority)))
        .scalars()
        .all()
    )


@router.get("/sources/registry")
async def source_registry():
    """Live registry from code (id, adapter, strategies, capabilities)."""
    from app.pipeline.collectors.registry import registry_snapshot

    return registry_snapshot()


@router.get("/tags", response_model=list[TagOut])
async def list_tags(
    session: SessionDep,
    category: str | None = None,
    q: str | None = None,
):
    statement = select(Tag)
    if category:
        statement = statement.where(Tag.category == category)
    if q:
        escaped_q = q.replace("%", r"\%").replace("_", r"\_")
        statement = statement.where(Tag.name.ilike(f"%{escaped_q}%"))
    return (
        (await session.execute(statement.order_by(Tag.category, Tag.name)))
        .scalars()
        .all()
    )


@router.get("/tags/categories")
async def tag_categories(session: SessionDep):
    rows = (
        await session.execute(
            select(Tag.category, func.count()).group_by(Tag.category)
        )
    ).all()
    return [{"category": c, "count": n} for c, n in rows]


@router.get("/condition-types", response_model=list[ConditionOption])
async def condition_types():
    """Describes the condition builder for the UI (no hardcoding client-side)."""
    return [
        ConditionOption(
            type=ConditionType.COUNTRY.value,
            operators=[ConditionOperator.IN.value, ConditionOperator.NOT_IN.value],
            unit_options=["all", "global"],
            description="One, several or all countries",
        ),
        ConditionOption(
            type=ConditionType.SOURCE.value,
            operators=[ConditionOperator.IN.value, ConditionOperator.NOT_IN.value],
            unit_options=["all"],
            description="One or several sources",
        ),
        ConditionOption(
            type=ConditionType.TAG.value,
            operators=[ConditionOperator.IN.value, ConditionOperator.NOT_IN.value],
            description="Predefined or custom tags",
        ),
        ConditionOption(
            type=ConditionType.KEYWORD.value,
            operators=[
                ConditionOperator.IN.value,
                ConditionOperator.NOT_IN.value,
            ],
            description="Include or exclude keywords",
        ),
        ConditionOption(
            type=ConditionType.GROWTH.value,
            operators=[
                ConditionOperator.GT.value,
                ConditionOperator.LT.value,
            ],
            description="Growth above or below a percentage",
        ),
        ConditionOption(
            type=ConditionType.ACTIVITY.value,
            operators=[
                ConditionOperator.GT.value,
                ConditionOperator.LT.value,
            ],
            description="Absolute activity threshold",
        ),
        ConditionOption(
            type=ConditionType.AGE.value,
            operators=[
                ConditionOperator.LT.value,
                ConditionOperator.GT.value,
            ],
            unit_options=["minutes", "hours", "days"],
            description="Signal age",
        ),
        ConditionOption(
            type=ConditionType.STATUS.value,
            operators=[ConditionOperator.IN.value],
            description="New / Rising / Breakout / Fading",
        ),
        ConditionOption(
            type=ConditionType.STRENGTH.value,
            operators=[
                ConditionOperator.GT.value,
                ConditionOperator.LT.value,
            ],
            description="Signal strength 0-100",
        ),
    ]
# -------------------------------------------------------- custom tags
custom_router = APIRouter(prefix="/custom-tags", tags=["custom-tags"])


@custom_router.get("", response_model=list[CustomTagOut])
async def list_custom_tags(user: CurrentUser, session: SessionDep):
    return (
        (
            await session.execute(
                select(CustomTag)
                .where(CustomTag.user_id == user.id)
                .order_by(CustomTag.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


@custom_router.post(
    "", response_model=CustomTagOut, status_code=status.HTTP_201_CREATED
)
async def create_custom_tag(
    payload: CustomTagCreate, user: CurrentUser, session: SessionDep
):
    tag = CustomTag(
        user_id=user.id,
        slug=slugify(payload.name),
        **_tag_fields(payload),
    )
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


def _tag_fields(payload: CustomTagCreate) -> dict:
    """Normalise every custom-tag field in one place."""
    return {
        "name": payload.name,
        "keywords": [normalize_text(k) for k in payload.keywords if k.strip()],
        "aliases": [normalize_text(a) for a in payload.aliases if a.strip()],
        "hashtags": [
            h.strip().lstrip("#").lower() for h in payload.hashtags if h.strip()
        ],
        "country_codes": [c.upper() for c in payload.country_codes],
        "source_ids": payload.source_ids,
        "excludes": [normalize_text(e) for e in payload.excludes if e.strip()],
        "exclude_hashtags": [
            h.strip().lstrip("#").lower()
            for h in payload.exclude_hashtags
            if h.strip()
        ],
        "exclude_countries": [c.upper() for c in payload.exclude_countries],
        "emoji": payload.emoji,
    }


@custom_router.post("/preview", response_model=dict)
async def preview_custom_tag(
    payload: CustomTagCreate, user: CurrentUser, session: SessionDep
):
    """Dry-run: how many stored signals would this custom tag match?"""
    from app.pipeline.matching.tag_matcher import CustomTagMatcher, MatchDocument

    fields = _tag_fields(payload)
    matcher = CustomTagMatcher([{**fields, "slug": "preview", "is_active": True}])

    from app.models import Signal
    from app.models.enums import SignalStatus

    signals = (
        (
            await session.execute(
                select(Signal)
                .where(Signal.status != SignalStatus.FADING)
                .order_by(Signal.strength.desc())
                .limit(400)
            )
        )
        .scalars()
        .unique()
        .all()
    )

    hits = []
    for signal in signals:
        document = MatchDocument(
            title=signal.title,
            description=signal.description or "",
            hashtags=signal.hashtags or [],
            category=signal.category,
            url=signal.source_url,
            source_metadata={
                "country_code": signal.country_code,
                "source_id": signal.source_id,
            },
        )
        if matcher.match(document):
            hits.append(
                {
                    "id": signal.id,
                    "title": signal.title,
                    "strength": signal.strength,
                    "country_code": signal.country_code,
                    "source_id": signal.source_id,
                }
            )
    return {"matched": len(hits), "items": hits[:20]}


@custom_router.patch("/{tag_id}", response_model=CustomTagOut)
async def update_custom_tag(
    tag_id: str, payload: CustomTagCreate, user: CurrentUser, session: SessionDep
):
    tag = await _get_custom_tag(session, user.id, tag_id)
    tag.slug = slugify(payload.name)
    for field, value in _tag_fields(payload).items():
        setattr(tag, field, value)
    await session.commit()
    await session.refresh(tag)
    return tag


@custom_router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_tag(tag_id: str, user: CurrentUser, session: SessionDep):
    tag = await _get_custom_tag(session, user.id, tag_id)
    await session.delete(tag)
    await session.commit()


async def _get_custom_tag(
    session: SessionDep, user_id: str, tag_id: str
) -> CustomTag:
    tag = (
        await session.execute(
            select(CustomTag).where(
                CustomTag.id == tag_id, CustomTag.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail="Custom tag not found")
    return tag