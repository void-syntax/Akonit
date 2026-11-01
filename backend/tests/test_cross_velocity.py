"""Comprehensive unit tests for Cross-Velocity Alpha Engine v3 (BullshitScrubber, Cross-Corroboration, Capital Backing, and Laya Classifier)."""

from __future__ import annotations

from app.pipeline.detection.cross_velocity import (
    BullshitScrubber,
    evaluate_cross_corroboration,
    calculate_capital_backing_factor,
    get_collector_family,
)
from app.pipeline.detection.scoring import compute_strength, strength_components
from app.pipeline.detection.metrics import GrowthMetrics
from app.ai.laya_classifier import _fallback_classification, _finite_float, LayaClassification


class TestBullshitScrubber:
    def test_scrubs_fluff_without_metrics(self):
        text = "This revolutionary game-changing platform is 100x disruptive and unprecedented."
        result = BullshitScrubber.evaluate(text)
        assert result["penalty_applied"] is True
        assert result["substance_factor"] < 0.5
        assert len(result["buzzwords"]) > 0
        assert result["has_metrics"] is False

    def test_allows_buzzwords_with_metrics(self):
        text = "This revolutionary game-changing platform achieved 50,000 GitHub stars and 1.5M downloads with $10M funding."
        result = BullshitScrubber.evaluate(text)
        assert result["has_metrics"] is True
        assert result["substance_factor"] >= 0.95
        assert len(result["buzzwords"]) > 0

    def test_clean_text_without_buzzwords(self):
        text = "Normal repository update fixing minor bugs in parser logic."
        result = BullshitScrubber.evaluate(text)
        assert result["penalty_applied"] is False
        assert result["substance_factor"] == 1.0
        assert len(result["buzzwords"]) == 0

    def test_hashtag_only_trends_are_demoted_without_rejecting_story_titles(self):
        tags = BullshitScrubber.evaluate("#LFC #UCL #YNWA")
        story = BullshitScrubber.evaluate("Central bank cuts interest rates")
        assert tags["penalty_applied"] is True
        assert tags["substance_factor"] == 0.35
        assert story["substance_factor"] == 1.0


class TestCrossCorroborationMatrix:
    def test_collector_family_mapping(self):
        assert get_collector_family("github-repo-trending") == "code"
        assert get_collector_family("huggingface-spaces") == "code"
        assert get_collector_family("reddit-r-cryptocurrency") == "social"
        assert get_collector_family("sec-edgar-form-d") == "finance"
        assert get_collector_family("polymarket-odds") == "prediction"

    def test_unicorn_signal_trigger_across_distinct_families(self):
        sources = ["github-repo", "huggingface-model"]
        result = evaluate_cross_corroboration(sources)
        assert result["family_count"] == 1  # both are code family

        sources_multi = ["github-repo", "sec-form-d", "polymarket-odds"]
        result_multi = evaluate_cross_corroboration(sources_multi)
        assert result_multi["family_count"] >= 2
        assert result_multi["is_unicorn"] is True
        assert result_multi["strength_multiplier"] == 1.15


class TestCapitalBackingFactor:
    def test_capital_backing_calculation(self):
        score_low = calculate_capital_backing_factor(0.0, 0.0)
        assert score_low == 0.0

        score_high = calculate_capital_backing_factor(5000000.0, 2000000.0)
        assert score_high > 10.0


class TestScoringIntegration:
    def test_compute_strength_with_unicorn_and_scrubber(self):
        metrics = GrowthMetrics(growth=100.0, velocity=50.0, absolute=1000.0, age_minutes=30.0)
        
        # Without unicorn or fluff
        strength_normal = compute_strength(metrics, sources=["github-repo"])
        
        # With multi-source unicorn multiplier (github + sec)
        strength_unicorn = compute_strength(metrics, sources=["github-repo", "sec-form-d"])
        assert strength_unicorn > strength_normal

        # With fluff penalty
        strength_fluff = compute_strength(
            metrics,
            sources=["github-repo"],
            text_content="This revolutionary game-changing tool is 100x guaranteed."
        )
        assert strength_fluff < strength_normal

    def test_strength_components_includes_metadata(self):
        metrics = GrowthMetrics(growth=50.0, velocity=20.0, absolute=500.0)
        comps = strength_components(
            metrics,
            sources=["github-repo", "polymarket-market"],
            text_content="Revolutionary AI framework with 10k stars",
            sec_volume=100000.0,
            polymarket_liquidity=50000.0,
        )
        assert "substance_factor" in comps
        assert "capital_backing" in comps
        assert "strength_multiplier" in comps
        assert comps["strength_multiplier"] == 1.15

    def test_one_source_gets_no_confirmation_bonus_and_ai_does_not_change_score(self):
        metrics = GrowthMetrics(growth=100.0, velocity=50.0, absolute=1000.0, age_minutes=30.0)
        single = compute_strength(metrics, cross_source_count=1, sources=["reddit"])
        multi = compute_strength(metrics, cross_source_count=3, sources=["reddit", "google-news"])
        with_ai = compute_strength(
            metrics, cross_source_count=1, sources=["reddit"], ai_priority_score=1.0
        )

        assert multi > single
        assert with_ai == single
        assert strength_components(metrics, cross_source_count=1, ai_priority_score=1.0)["ai_boost"] == 0.0


class TestLayaClassifierEnhancements:
    def test_strong_activity_does_not_override_explicit_noise_judgment(self):
        from app.ai.laya_classifier import _normalize_priority

        assert _normalize_priority("noise", "actionable", False) == "noise"
        assert _normalize_priority("critical", "fluff", False) == "noise"

    def test_laya_cache_changes_when_trend_state_changes(self):
        from app.ai.laya_classifier import _classification_cache_key

        first = _classification_cache_key(
            "same", "same description", "test", 0, 10, "new"
        )
        updated = _classification_cache_key(
            "same", "same description", "test", 90, 90, "breakout"
        )
        assert first != updated

    def test_fallback_classification_actionability_and_risk_reward(self):
        classification: LayaClassification = _fallback_classification(
            strength=80.0, growth=50.0, status="BREAKOUT", is_thin=False
        )
        assert "actionability_potential" in classification
        assert "risk_reward_ratio" in classification
        assert classification["actionability_potential"] >= 80.0
        assert classification["risk_reward_ratio"] > 1.0
        assert classification["alpha_score"] == 0.0
        assert classification["monetization_potential"] == 0.0
        assert classification["breakout_probability"] == 0.0

    def test_model_output_clamps_invalid_or_out_of_range_numbers(self):
        assert _finite_float(float("nan"), 0.3, 0.0, 1.0) == 0.3
        assert _finite_float(float("inf"), 0.3, 0.0, 1.0) == 0.3
        assert _finite_float(4, 0.3, 0.0, 1.0) == 1.0
