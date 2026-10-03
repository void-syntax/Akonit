"""Unit tests for the condition engine and tag matching."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.enums import SignalStatus
from app.pipeline.matching.tag_matcher import (
    CustomTagMatcher,
    MatchDocument,
    build_default_matcher,
)
from app.pipeline.normalization.normalizer import (
    canonicalize_url,
    normalize_text,
    similarity,
    simhash,
    slugify,
)
from app.radar.ast import normalize_ast
from app.radar.evaluator import evaluate_group


class FakeSignal:
    """Minimal object satisfying the evaluator protocol."""

    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "")
        self.description = kwargs.get("description", "")
        self.category = kwargs.get("category")
        self.hashtags = kwargs.get("hashtags", [])
        self.country_code = kwargs.get("country_code")
        self.source_id = kwargs.get("source_id", "tiktok")
        self.source_url = kwargs.get("source_url", "")
        self.growth = kwargs.get("growth", 0.0)
        self.current_activity = kwargs.get("current_activity", 0.0)
        self.strength = kwargs.get("strength", 0.0)
        self.status = kwargs.get("status", SignalStatus.NEW)
        self.first_seen_at = kwargs.get("first_seen_at", datetime.now(UTC))
        self.tag_slugs = set(kwargs.get("tag_slugs", set()))
        self.keywords = list(self.tag_slugs)


def conditions(payload: dict):
    return normalize_ast(payload)


class TestConditionEngine:
    def test_country_in(self):
        group = conditions(
            {"type": "country", "operator": "IN", "value": ["KR", "JP"]}
        )
        assert evaluate_group(group, FakeSignal(country_code="KR"))
        assert not evaluate_group(group, FakeSignal(country_code="US"))

    def test_all_countries_wildcard(self):
        group = conditions(
            {"type": "country", "operator": "IN", "value": "ALL", "unit": "all"}
        )
        assert evaluate_group(group, FakeSignal(country_code="DE"))

    def test_source_and_growth(self):
        group = conditions(
            {
                "op": "AND",
                "children": [
                    {"type": "source", "operator": "IN", "value": ["tiktok"]},
                    {"type": "growth", "operator": "GT", "value": 100},
                ],
            }
        )
        assert evaluate_group(group, FakeSignal(source_id="tiktok", growth=250))
        assert not evaluate_group(
            group, FakeSignal(source_id="tiktok", growth=50)
        )
        assert not evaluate_group(
            group, FakeSignal(source_id="youtube", growth=250)
        )

    def test_not_is_exclusion(self):
        group = conditions(
            {
                "op": "NOT",
                "children": [
                    {"type": "tag", "operator": "IN", "value": ["cosplay"]}
                ],
            }
        )
        assert evaluate_group(group, FakeSignal(tag_slugs={"makeup"}))
        assert not evaluate_group(group, FakeSignal(tag_slugs={"cosplay"}))

    def test_and_or_combination(self):
        group = conditions(
            {
                "op": "AND",
                "children": [
                    {
                        "op": "OR",
                        "children": [
                            {"type": "country", "operator": "IN", "value": ["KR"]},
                            {"type": "country", "operator": "IN", "value": ["JP"]},
                        ],
                    },
                    {"type": "strength", "operator": "GT", "value": 60},
                ],
            }
        )
        assert evaluate_group(group, FakeSignal(country_code="JP", strength=75))
        assert not evaluate_group(
            group, FakeSignal(country_code="JP", strength=40)
        )
        assert not evaluate_group(
            group, FakeSignal(country_code="US", strength=90)
        )


class TestTagMatching:
    def setup_method(self):
        self.matcher = build_default_matcher()

    def test_hashtag_match(self):
        doc = MatchDocument(title="#kbeauty trend", hashtags=["kbeauty"])
        slugs = {m.slug for m in self.matcher.match(doc)}
        assert "makeup" in slugs

    def test_keyword_match(self):
        doc = MatchDocument(title="New lipstick set tutorial", description="makeup")
        slugs = {m.slug for m in self.matcher.match(doc)}
        assert "makeup" in slugs

    def test_alias_match(self):
        doc = MatchDocument(
            title="Korean beauty routine", description="glass skin"
        )
        slugs = {m.slug for m in self.matcher.match(doc)}
        assert {"makeup", "skincare"} & slugs

    def test_ai_terms(self):
        doc = MatchDocument(
            title="New open source AI agent", description="free ai tool"
        )
        slugs = {m.slug for m in self.matcher.match(doc)}
        assert {"ai-agents", "free-ai", "open-source-ai", "ai"} & slugs


class TestCustomTags:
    def make(self) -> CustomTagMatcher:
        return CustomTagMatcher(
            [
                {
                    "slug": "korean-makeup",
                    "is_active": True,
                    "keywords": ["korean makeup", "k-beauty"],
                    "hashtags": ["kbeauty"],
                    "country_codes": ["KR"],
                    "source_ids": ["tiktok"],
                    "excludes": ["cosplay"],
                }
            ]
        )

    def test_matches_inside_scope(self):
        hit = self.make().match(
            MatchDocument(
                title="#kbeauty viral",
                source_metadata={"country_code": "KR", "source_id": "tiktok"},
            )
        )
        assert hit and hit[0].slug == "custom:korean-makeup"

    def test_exclude_blocks_match(self):
        assert not self.make().match(
            MatchDocument(
                title="#kbeauty cosplay tutorial",
                source_metadata={"country_code": "KR", "source_id": "tiktok"},
            )
        )

    def test_country_scope_respected(self):
        assert not self.make().match(
            MatchDocument(
                title="#kbeauty",
                source_metadata={
                    "country_code": "US",
                    "source_id": "tiktok",
                },
            )
        )

    def test_source_scope_respected(self):
        assert not self.make().match(
            MatchDocument(
                title="#kbeauty",
                source_metadata={
                    "country_code": "KR",
                    "source_id": "youtube",
                },
            )
        )


class TestNormalization:
    def test_normalize_text(self):
        assert normalize_text("  K-Beauty!!!  ") == "k-beauty"

    def test_canonicalize_url_strips_tracking(self):
        a = canonicalize_url("https://x.com/tag/makeup/?utm_source=t&fbclid=1")
        b = canonicalize_url("https://x.com/tag/makeup")
        assert a == b

    def test_simhash_similarity(self):
        """64-bit simhash: identical text scores 1.0, unrelated text stays low."""
        a = simhash("new viral makeup trend in korea")
        b = simhash("new viral makeup trend in korea")
        c = simhash("quarterly revenue report for banks")
        assert similarity(a, b) == 1.0
        # 64-bit hashes land near 0.5 for unrelated text; near 1.0 for duplicates.
        assert similarity(a, c) < 0.75

    def test_slugify(self):
        assert slugify("New Makeup Trend!") == "new-makeup-trend"
