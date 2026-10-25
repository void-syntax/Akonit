"""Tests for SimHash deduplication and anomaly detection modules."""

from __future__ import annotations

import pytest
from app.pipeline.simhash import (
    SimHashDeduplicator,
    compute_simhash,
    hamming_distance,
    normalize_url,
    get_deduplicator,
)
from app.pipeline.detection.anomaly import (
    SpikeDetector,
    check_spike,
    AnomalyResult,
)


# ---------------------------------------------------------------------------
# SimHash tests
# ---------------------------------------------------------------------------

class TestComputeSimhash:
    def test_same_text_same_fingerprint(self):
        text = "artificial intelligence startup product hunt"
        assert compute_simhash(text) == compute_simhash(text)

    def test_different_text_different_fingerprint(self):
        a = compute_simhash("completely different topic")
        b = compute_simhash("artificial intelligence startup")
        # Very likely different (probabilistic — but these are very different)
        assert a != b

    def test_empty_text_returns_zero(self):
        assert compute_simhash("") == 0

    def test_fingerprint_is_64bit(self):
        fp = compute_simhash("some text here")
        assert 0 <= fp < (1 << 64)


class TestHammingDistance:
    def test_identical_distance_zero(self):
        assert hamming_distance(0b1010, 0b1010) == 0

    def test_single_bit_diff(self):
        assert hamming_distance(0b1010, 0b1011) == 1

    def test_all_bits_differ(self):
        assert hamming_distance(0, (1 << 64) - 1) == 64


class TestSimHashDeduplicator:
    def test_first_doc_not_duplicate(self):
        d = SimHashDeduplicator()
        assert not d.is_duplicate("doc1", "machine learning trends 2026")

    def test_same_id_is_duplicate(self):
        d = SimHashDeduplicator()
        d.is_duplicate("doc1", "machine learning trends 2026")
        assert d.is_duplicate("doc1", "machine learning trends 2026")

    def test_near_identical_text_is_duplicate(self):
        d = SimHashDeduplicator(threshold=3)
        text1 = "new ai tool released today free to use"
        text2 = "new ai tool released today free to use!"  # one char diff
        d.is_duplicate("a", text1)
        # Near-identical — should be flagged
        assert d.is_duplicate("b", text2)

    def test_very_different_text_not_duplicate(self):
        d = SimHashDeduplicator(threshold=3)
        d.is_duplicate("a", "python machine learning neural network")
        assert not d.is_duplicate("b", "fashion trend makeup skincare beauty")

    def test_size_bounded_by_maxsize(self):
        d = SimHashDeduplicator(maxsize=5)
        for i in range(10):
            d.is_duplicate(f"doc{i}", f"unique document number {i} with some extra text")
        assert d.size <= 5

    def test_stats_track_correctly(self):
        d = SimHashDeduplicator()
        d.is_duplicate("a", "hello world this is a test document")
        d.is_duplicate("a", "hello world this is a test document")  # duplicate
        stats = d.stats
        assert stats["total"] == 2
        assert stats["duplicates"] == 1

    def test_similar_to_returns_nearest(self):
        d = SimHashDeduplicator()
        d.add("doc1", "artificial intelligence startup launch")
        d.add("doc2", "football match score result")
        results = d.similar_to("AI startup launched today")
        assert len(results) > 0
        # doc1 should be closer
        assert results[0][0] == "doc1"


class TestNormalizeUrl:
    def test_strips_utm_params(self):
        url = "https://example.com/post?utm_source=twitter&utm_campaign=launch"
        assert "utm" not in normalize_url(url)

    def test_strips_fragment(self):
        url = "https://example.com/page#section2"
        assert "#" not in normalize_url(url)

    def test_lowercases_url(self):
        url = "HTTPS://EXAMPLE.COM/Path"
        assert normalize_url(url) == normalize_url(url).lower()

    def test_preserves_path(self):
        url = "https://github.com/owner/repo"
        assert "owner/repo" in normalize_url(url)


# ---------------------------------------------------------------------------
# Anomaly detection tests
# ---------------------------------------------------------------------------

class TestSpikeDetector:
    def test_no_spike_with_few_samples(self):
        detector = SpikeDetector()
        result = detector.update(100.0)
        assert not result.is_spike
        assert result.sample_count == 1

    def test_flat_signal_no_spike(self):
        detector = SpikeDetector(threshold=3.5)
        for _ in range(30):
            result = detector.update(50.0)
        assert not result.is_spike

    def test_spike_detected_after_warmup(self):
        detector = SpikeDetector(threshold=3.5, window=30)
        # Feed 25 normal values
        for _ in range(25):
            detector.update(10.0)
        # Feed extreme spike
        result = detector.update(500.0)
        assert result.is_spike

    def test_z_score_positive_for_spike(self):
        detector = SpikeDetector(threshold=3.5, window=30)
        for _ in range(25):
            detector.update(10.0)
        result = detector.update(1000.0)
        assert result.z_score > 3.5

    def test_ewma_converges(self):
        detector = SpikeDetector(alpha=0.3)
        for _ in range(20):
            result = detector.update(100.0)
        assert abs(result.ewma - 100.0) < 5.0

    def test_reset_clears_state(self):
        detector = SpikeDetector()
        for _ in range(10):
            detector.update(50.0)
        detector.reset()
        result = detector.update(50.0)
        assert result.sample_count == 1

    def test_result_is_named_tuple(self):
        detector = SpikeDetector()
        result = detector.update(10.0)
        assert isinstance(result, AnomalyResult)
        assert hasattr(result, "is_spike")
        assert hasattr(result, "z_score")
        assert hasattr(result, "ewma")
        assert hasattr(result, "sample_count")


class TestCheckSpike:
    def test_module_level_function_works(self):
        for _ in range(25):
            check_spike("test_source", 10.0, "views")
        result = check_spike("test_source", 999.0, "views")
        assert result.is_spike

    def test_different_sources_independent(self):
        for _ in range(25):
            check_spike("source_a", 10.0)
        for _ in range(25):
            check_spike("source_b", 1000.0)
        # source_a should spike at 500, source_b stays normal
        result_a = check_spike("source_a", 500.0)
        result_b = check_spike("source_b", 1000.0)
        assert result_a.is_spike
        assert not result_b.is_spike
