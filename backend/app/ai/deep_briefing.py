"""Create a lightweight, evidence-aware template summary for a signal."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Signal
from app.models.signals import IntelligenceBriefing  # To be added or defined

logger = get_logger("ai.deep_briefing")


class IntelligenceBriefingDict(TypedDict):
    core_thesis: str
    alpha_potential: str
    monetization_strategy: str
    risk_analysis: str
    sources_synthesized: list[str]
    confidence_score: float
    model_used: str


async def synthesize_deep_briefing(session: AsyncSession, signal_id: str) -> IntelligenceBriefing | None:
    """Create an evidence-aware template summary for a high-priority signal."""
    signal = await session.get(Signal, signal_id)
    if not signal:
        logger.warning("Signal %s not found for deep briefing", signal_id)
        return None

    # Check if briefing already exists
    existing = (
        await session.execute(
            select(IntelligenceBriefing).where(IntelligenceBriefing.signal_id == signal_id)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    # Check if signal status or priority warrants deep briefing
    is_critical_or_unicorn = (
        signal.status.value in ["UNICORN_SIGNAL", "BREAKOUT"]
        or signal.ai_priority == "critical"
        or signal.strength >= 80.0
    )

    if not is_critical_or_unicorn:
        logger.debug("Signal %s does not meet critical/unicorn criteria for deep briefing", signal_id)
        return None

    logger.info("Creating signal briefing for %s (%s)", signal.title, signal.id)

    # Synthesize multi-source data
    cross_urls = signal.cross_source_urls or [signal.source_url]
    keywords = signal.keywords or []
    category = signal.ai_category or signal.category or "unspecified"

    # The current implementation is a transparent template, not an LLM.
    core_thesis = (
        f"Observed trend: '{signal.title}' ({category}). Current strength is "
        f"{signal.strength:.1f}/100 and reported growth is {signal.growth:+.1f}%. "
        f"The record contains {len(cross_urls)} source references; verify they are independent "
        "and confirm the underlying publication dates before treating this as corroborated."
    )

    alpha_potential = (
        f"Trend strength: {signal.strength:.1f}/100; this measures observed activity, "
        "not investment alpha or expected return. "
        f"Topic: {keywords[0] if keywords else category}. "
        f"Observed source references: {len(cross_urls)}; corroboration is not proof of institutional activity."
    )

    monetization_strategy = (
        "No commercial plan can be inferred from activity alone. Verify user demand, "
        "pricing, competition, licensing, and operating costs before estimating a business case."
    )

    if signal.ai_classified_at is None:
        noise_assessment = "Laya did not classify this signal; noise risk is unknown."
    else:
        noise_assessment = (
            f"Noise estimate: {signal.ai_noise_probability * 100:.1f}%; "
            "this is an uncalibrated model score, not a probability of failure."
        )

    risk_analysis = (
        f"- **Evidence gaps**: Check primary sources and verify publication time and source independence.\n"
        f"- **Commercial uncertainty**: Trend activity alone does not establish demand, revenue, or investability.\n"
        f"- **Noise indicator**: {noise_assessment}"
    )

    briefing = IntelligenceBriefing(
        signal_id=signal.id,
        core_thesis=core_thesis,
        alpha_potential=alpha_potential,
        monetization_strategy=monetization_strategy,
        risk_analysis=risk_analysis,
        sources_synthesized=cross_urls,
        confidence_score=min(max(signal.confidence, 0.0), 1.0),
        model_used="template-synthesis-v2",
        created_at=datetime.now(UTC),
    )

    session.add(briefing)
    await session.flush()
    logger.info("Created signal briefing for %s", signal.id)
    return briefing
