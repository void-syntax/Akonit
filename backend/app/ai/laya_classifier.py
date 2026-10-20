"""Laya AI signal classifier with enhanced data quality and actionability scrutiny.

Laya is a non-autoregressive decision model that classifies signals in ~33ms
using a single forward pass. No text generation, no hallucination, no LLM overhead.
Enhanced to actively penalize fluff, thin content, and code spam, while boosting
actionable tech and investment signals.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import TypedDict

logger = logging.getLogger("ai.laya")

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="laya")


class LayaClassification(TypedDict):
    priority: str          # "critical" | "watch" | "noise"
    priority_score: float  # 0.0 - 1.0
    category: str          # "tech" | "social" | "finance" | "culture" | "science" | "politics" | "other"
    should_notify: float   # 0.0 - 1.0 probability of yes
    noise_probability: float  # 0.0 - 1.0 higher = more likely noise
    trending_score: float  # 0.0 - 1.0
    alpha_score: float     # 0.0 - 100.0 institutional alpha score
    monetization_potential: float  # 0.0 - 100.0 financial/developer monetization potential
    breakout_probability: float  # 0.0 - 1.0 exponential breakout probability
    actionability_potential: float  # 0.0 - 100.0 actionability potential
    risk_reward_ratio: float       # numerical risk-to-reward ratio (1.0 - 10.0+)
    model_used: str


LAYA_QUESTIONS = {
    "priority": {
        "type": "choice",
        "instructions": "What is the priority level of this trending signal?",
        "criteria": {
            "critical": "Breaking trend, viral, high growth, needs immediate attention, BREAKOUT level",
            "watch": "Interesting signal, moderate growth, worth monitoring, RISING level",
            "noise": "Low quality, repetitive, spam, low activity, thin content, or irrelevant",
        },
    },
    "actionability": {
        "type": "choice",
        "instructions": "Is this signal actionable with clear technical, developer, or investment value?",
        "criteria": {
            "actionable": "High-value tech release, genuine breakout trend, investment opportunity, or deep substance",
            "fluff": "Thin snippet, auto-generated boilerplate, pure code without context, or low-value spam",
        },
    },
    "category": {
        "type": "choice",
        "instructions": "What is the primary topic category of this signal?",
        "criteria": {
            "tech": "Technology, software, AI, programming, startups, gadgets",
            "social": "Social media trends, viral content, influencers, entertainment, celebrities, TikTok, YouTube",
            "finance": "Finance, crypto, stocks, markets, economy, business, investment",
            "culture": "Culture, fashion, food, lifestyle, music, art, sports",
            "science": "Science, research, health, medicine, environment, space",
            "politics": "Politics, government, policy, news, world events",
            "other": "Anything else not fitting above categories",
        },
    },
    "should_notify": {
        "type": "noul",
        "instructions": "Should the user be immediately notified about this signal? Yes only for truly significant, urgent, or rare trends.",
    },
    "is_noise": {
        "type": "noul",
        "instructions": "Is this signal likely noise, spam, repetitive content, or irrelevant low-quality data?",
    },
    "trending_confidence": {
        "type": "score",
        "instructions": "How confident are you that this is a genuine trending signal and not a fluke?",
        "criteria": ["likely fluke or noise", "possibly trending", "clearly trending and significant"],
    },
    "alpha_potential": {
        "type": "score",
        "instructions": "Rate the institutional alpha and investment/developer value of this signal from 0 to 100.",
        "criteria": ["low alpha / noise", "moderate developer or market interest", "exceptional institutional alpha and breakout potential"],
    },
    "monetization": {
        "type": "score",
        "instructions": "Estimate the financial or developer monetization potential of this technology, product, or trend from 0 to 100.",
        "criteria": ["no clear commercial model", "moderate commercial viability", "high monetization and venture/developer scale"],
    },
    "actionability_potential": {
        "type": "score",
        "instructions": "Rate the concrete actionability and execution potential of this signal from 0 to 100.",
        "criteria": ["vague or non-actionable", "partially actionable or speculative", "highly actionable with clear execution steps or deployment"],
    },
    "risk_reward_ratio": {
        "type": "score",
        "instructions": "Estimate the risk-to-reward ratio (scale 1 to 10, where higher means superior asymmetric upside relative to downside risk).",
        "criteria": ["poor risk/reward", "neutral or balanced", "exceptional asymmetric risk/reward upside"],
    },
}


@lru_cache(maxsize=1)
def _get_router():
    """Load Laya router once and cache. Thread-safe via lru_cache."""
    try:
        from laya import Router  # type: ignore[import-untyped]
        logger.info("Loading Laya AI router...")
        router = Router(preload=False)
        logger.info("Laya AI router ready")
        return router
    except ImportError:
        logger.warning("laya not installed — AI classification disabled")
        return None
    except Exception as exc:
        logger.warning("Laya failed to load: %r — AI classification disabled", exc)
        return None


def _classify_sync(
    title: str,
    description: str,
    source_id: str,
    growth: float,
    strength: float,
    status: str,
) -> LayaClassification:
    """Run Laya classification synchronously (called from thread pool)."""
    import time
    from app.core.metrics import laya_classification_duration_seconds

    start_time = time.time()
    try:
        text_combined = f"{title} {description}".strip()
        words = text_combined.split()
        is_thin = len(words) < 6

        router = _get_router()
        if router is None or is_thin:
            return _fallback_classification(strength, growth, status, is_thin)

        state = {
            "title": title,
            "description": description[:500] if description else "",
            "source": source_id,
            "growth_pct": f"{growth:+.1f}%",
            "strength": f"{strength:.1f}/100",
            "status": status,
        }

        try:
            result = router.predict(state, LAYA_QUESTIONS)
            answers = result.get("answers", {})

            priority_ans = answers.get("priority", {})
            action_ans = answers.get("actionability", {})
            category_ans = answers.get("category", {})
            notify_ans = answers.get("should_notify", {})
            noise_ans = answers.get("is_noise", {})
            trending_ans = answers.get("trending_confidence", {})

            alpha_ans = answers.get("alpha_potential", {})
            monet_ans = answers.get("monetization", {})
            actionability_pot_ans = answers.get("actionability_potential", {})
            risk_reward_ans = answers.get("risk_reward_ratio", {})

            priority = priority_ans.get("choice", "watch")
            priority_probs = priority_ans.get("probs", {})
            priority_score = priority_probs.get(priority, 0.5)

            actionability_choice = action_ans.get("choice", "actionable")
            if actionability_choice == "fluff" or is_thin:
                priority = "noise"
                priority_score = 0.85

            # Smart override for high breakout or high strength signals with substance
            if (status == "breakout" or strength >= 70) and not is_thin:
                if priority == "noise":
                    priority = "critical"
                    priority_score = max(priority_score, 0.85)
            elif (status == "rising" or strength >= 45) and not is_thin:
                if priority == "noise":
                    priority = "watch"
                    priority_score = max(priority_score, 0.65)

            category = category_ans.get("choice", "other")
            should_notify = notify_ans.get("noul", 0.3)
            if actionability_choice == "fluff":
                should_notify = min(should_notify, 0.1)

            noise_probability = noise_ans.get("noul", 0.3)
            if actionability_choice == "fluff" or is_thin:
                noise_probability = max(noise_probability, 0.9)

            trending_score = (trending_ans.get("score", 1.0) or 1.0) / 2.0
            alpha_score = float(alpha_ans.get("score", strength) or strength)
            monetization_potential = float(monet_ans.get("score", strength * 0.8) or (strength * 0.8))
            actionability_potential = float(actionability_pot_ans.get("score", strength) or strength)
            risk_reward_ratio = float(risk_reward_ans.get("score", 3.5) or 3.5)
            if risk_reward_ratio > 10.0:
                risk_reward_ratio = max(1.0, risk_reward_ratio / 10.0)

            breakout_probability = min(max((strength / 100.0) * (1.0 - noise_probability), 0.0), 1.0)
            model_used = result.get("routing", {}).get("model", "unknown")

            return LayaClassification(
                priority=priority,
                priority_score=float(priority_score),
                category=category,
                should_notify=float(should_notify),
                noise_probability=float(noise_probability),
                trending_score=float(trending_score),
                alpha_score=alpha_score,
                monetization_potential=monetization_potential,
                breakout_probability=breakout_probability,
                actionability_potential=actionability_potential,
                risk_reward_ratio=risk_reward_ratio,
                model_used=model_used,
            )
        except Exception as exc:
            logger.warning("Laya prediction failed: %r", exc)
            return _fallback_classification(strength, growth, status, is_thin)
    finally:
        laya_classification_duration_seconds.observe(time.time() - start_time)


def _fallback_classification(strength: float, growth: float, status: str, is_thin: bool = False) -> LayaClassification:
    """Rule-based fallback when Laya is unavailable or content is thin."""
    if is_thin:
        return LayaClassification(
            priority="noise",
            priority_score=0.9,
            category="other",
            should_notify=0.0,
            noise_probability=0.95,
            trending_score=0.1,
            alpha_score=5.0,
            monetization_potential=5.0,
            breakout_probability=0.01,
            actionability_potential=5.0,
            risk_reward_ratio=1.0,
            model_used="fallback-thin",
        )

    if strength >= 70 or status == "BREAKOUT":
        priority = "critical"
        priority_score = 0.85
        should_notify = 0.8
        alpha_score = max(strength, 85.0)
        monetization_potential = 80.0
        breakout_probability = 0.9
        actionability_potential = max(strength, 85.0)
        risk_reward_ratio = 6.5
    elif strength >= 45 or status == "RISING":
        priority = "watch"
        priority_score = 0.65
        should_notify = 0.4
        alpha_score = max(strength, 60.0)
        monetization_potential = 55.0
        breakout_probability = 0.5
        actionability_potential = max(strength, 60.0)
        risk_reward_ratio = 4.0
    elif status == "NEW":
        priority = "watch"
        priority_score = 0.5
        should_notify = 0.2
        alpha_score = max(strength, 40.0)
        monetization_potential = 40.0
        breakout_probability = 0.25
        actionability_potential = max(strength, 40.0)
        risk_reward_ratio = 3.0
    else:
        priority = "noise" if strength < 30 else "watch"
        priority_score = 0.4
        should_notify = 0.1
        alpha_score = strength
        monetization_potential = 20.0
        breakout_probability = 0.1
        actionability_potential = strength
        risk_reward_ratio = 2.0

    return LayaClassification(
        priority=priority,
        priority_score=priority_score,
        category="other",
        should_notify=should_notify,
        noise_probability=0.3 if priority != "noise" else 0.7,
        trending_score=min(strength / 100.0, 1.0),
        alpha_score=alpha_score,
        monetization_potential=monetization_potential,
        breakout_probability=breakout_probability,
        actionability_potential=actionability_potential,
        risk_reward_ratio=risk_reward_ratio,
        model_used="fallback",
    )


async def classify_signal(
    title: str,
    description: str,
    source_id: str,
    growth: float | None = 0.0,
    strength: float | None = 0.0,
    status: str | None = "new",
) -> LayaClassification:
    """Async wrapper with cache-aside pattern for Laya classifications."""
    from app.core.cache import cache_aside
    import hashlib

    cache_key = f"laya:classify:{hashlib.md5(f'{title}:{description}:{source_id}:{growth}:{strength}:{status}'.encode('utf-8')).hexdigest()}"

    async def _fetch():
        loop = asyncio.get_running_loop()
        safe_growth = float(growth or 0.0)
        safe_strength = float(strength or 0.0)
        safe_status = str(status or "new")
        return await loop.run_in_executor(
            _executor,
            _classify_sync,
            title,
            description,
            source_id,
            safe_growth,
            safe_strength,
            safe_status,
        )

    return await cache_aside(cache_key, _fetch, ttl_seconds=3600)


async def warm_up() -> bool:
    """Pre-load the Laya checkpoint at startup. Call once from app lifespan."""
    loop = asyncio.get_running_loop()
    router = await loop.run_in_executor(_executor, _get_router)
    return router is not None
