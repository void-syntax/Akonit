"""Cross-Velocity Alpha Engine v3: Multi-source cross-corroboration, BullshitScrubber, and Capital Backing Factor."""

from __future__ import annotations

import math
import re
from typing import Any, Sequence

# Define distinct collector families
COLLECTOR_FAMILIES = {
    "github": "code",
    "huggingface": "code",
    "gitlab": "code",
    "reddit": "social",
    "bluesky": "social",
    "mastodon": "social",
    "twitter": "social",
    "x": "social",
    "instagram": "social",
    "tiktok": "social",
    "youtube": "social",
    "polymarket": "prediction",
    "sec": "finance",
    "news": "media",
    "rss": "media",
    "gdelt": "media",
    "google_news": "media",
    "rss_news": "media",
    "google_trends": "search_trends",
    "arxiv": "research",
    "hackernews": "social",
    "producthunt": "product",
    "stackoverflow": "developer_community",
    "lobsters": "developer_community",
    "devto": "developer_community",
    "discord": "social",
    "telegram": "social",
}

BUZZWORDS = {
    "revolutionary",
    "game-changing",
    "game changing",
    "next-gen",
    "next gen",
    "guaranteed",
    "100x",
    "disruptive",
    "paradigm-shifting",
    "paradigm shifting",
    "unprecedented",
    "ultimate",
    "magic",
    "transformational",
}

# Regex to find quantitative metrics (numbers followed by keywords or symbols like $, stars, downloads, etc.)
QUANTITATIVE_PATTERNS = [
    r"\d+[\d,]*\s*(?:stars?|downloads?|forks?|users?|commits?|holders?|liquidity|volume|\$|usd|million|billion|k|m|b|tvl|holders|addresses|transactions)\b",
    r"\$\s*\d+[\d,]*",
    r"\b(?:raised|funding|valuation|market cap|tvl|revenue|arr)\b.*?\d+",
    r"\d+\.\d+\s*(?:x|%|pts|accuracy|pp|latency|ms)\b",
    r"\b\d{4,}\b",  # large raw counts like 10000+ stars or users
]


class BullshitScrubber:
    """Scrubs and penalizes buzzwords that lack quantitative backing."""
    
    @staticmethod
    def evaluate(text: str) -> dict[str, Any]:
        if not text:
            return {
                "buzzwords": [],
                "has_metrics": False,
                "substance_factor": 1.0,
                "penalty_applied": False,
            }
            
        text_lower = text.lower()
        found_buzzwords = [bw for bw in BUZZWORDS if bw in text_lower]
        
        has_metrics = False
        for pattern in QUANTITATIVE_PATTERNS:
            if re.search(pattern, text_lower):
                has_metrics = True
                break
                
        # Calculate substance factor
        if found_buzzwords and not has_metrics:
            # Severe penalty for pure fluff
            substance_factor = 0.4
            penalty_applied = True
        elif found_buzzwords and has_metrics:
            # Buzzwords present but backed by quantitative metrics -> mild penalty reduction
            substance_factor = 0.95
            penalty_applied = False
        else:
            substance_factor = 1.0
            penalty_applied = False
            
        return {
            "buzzwords": found_buzzwords,
            "has_metrics": has_metrics,
            "substance_factor": substance_factor,
            "penalty_applied": penalty_applied,
        }


def get_collector_family(source_id: str) -> str:
    """Map a source ID or collector name to its distinct collector family."""
    if not source_id:
        return "unknown"
    source_lower = source_id.lower()
    for key, family in COLLECTOR_FAMILIES.items():
        if key in source_lower:
            return family
    return source_lower


def evaluate_cross_corroboration(sources: Sequence[str]) -> dict[str, Any]:
    """Evaluate multi-source cross-corroboration across distinct collector families.
    
    Two independent families are useful corroboration, not proof. Apply a
    modest multiplier so reposts or broad low-quality sources cannot dominate.
    """
    families = {get_collector_family(src) for src in sources if src}
    distinct_family_count = len(families)
    
    is_unicorn = distinct_family_count >= 2
    multiplier = 1.15 if is_unicorn else 1.0
    
    return {
        "distinct_families": list(families),
        "family_count": distinct_family_count,
        "is_unicorn": is_unicorn,
        "strength_multiplier": multiplier,
    }


def calculate_capital_backing_factor(sec_volume: float = 0.0, polymarket_liquidity: float = 0.0) -> float:
    """Calculate capital backing factor based on SEC Form D/Form 4 volume and Polymarket liquidity."""
    sec_score = min(math.log10(max(sec_volume, 0.0) + 1.0) / 6.0, 1.0) * 50.0
    poly_score = min(math.log10(max(polymarket_liquidity, 0.0) + 1.0) / 6.0, 1.0) * 50.0
    return round(sec_score + poly_score, 2)
