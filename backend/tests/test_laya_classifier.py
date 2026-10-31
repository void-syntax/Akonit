from __future__ import annotations

from app.ai import laya_classifier


def test_thin_content_uses_noise_fallback_without_loading_laya(monkeypatch):
    def fail_if_loaded():
        raise AssertionError("Laya model should not load for thin content")

    monkeypatch.setattr(laya_classifier, "_get_router", fail_if_loaded)

    result = laya_classifier._classify_sync(
        title="#newtrend",
        description="",
        source_id="x_trends",
        growth=0.0,
        strength=8.9,
        status="NEW",
    )

    assert result["priority"] == "noise"
    assert result["noise_probability"] == 0.95
    assert result["model_used"] == "fallback-thin"


def test_critical_label_requires_engine_evidence():
    assert laya_classifier._gate_critical_priority(
        "critical",
        0.5,
        0.58,
        strength=14.0,
        status="NEW",
        minimum_strength=45.0,
    ) == ("watch", 0.5, 0.3)

    assert laya_classifier._gate_critical_priority(
        "critical",
        0.8,
        0.7,
        strength=72.0,
        status="BREAKOUT",
        minimum_strength=45.0,
    ) == ("critical", 0.8, 0.7)
