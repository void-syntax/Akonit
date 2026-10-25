"""Lightweight SimHash-based near-duplicate detection for Signal Radar.

SimHash позволяет обнаруживать почти-дубликаты за O(1) на документ
без хранения всех документов в памяти.

Принцип:
- Каждый документ хешируется в 64-битное целое (fingerprint).
- Два документа считаются дубликатами, если расстояние Хэмминга ≤ порога
  (по умолчанию 3 бита из 64 — ~95% сходства).
- Fingerprints хранятся в ограниченном по размеру LRU-словаре.

Реализован на чистом Python без внешних зависимостей.
RAM-footprint: ~100 байт/документ × maxsize = 1.6 МБ при maxsize=16000.
"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict

from app.core.logging import get_logger

logger = get_logger("app.pipeline.simhash")

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.ASCII)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _token_hash(token: str) -> int:
    digest = hashlib.md5(token.encode(), usedforsecurity=False).digest()
    return int.from_bytes(digest[:8], "big")


def compute_simhash(text: str) -> int:
    """Compute a 64-bit SimHash fingerprint for *text*."""
    vector = [0] * 64
    tokens = _tokenize(text)
    if not tokens:
        return 0
    for token in tokens:
        h = _token_hash(token)
        for i in range(64):
            if h & (1 << i):
                vector[i] += 1
            else:
                vector[i] -= 1
    fingerprint = 0
    for i in range(64):
        if vector[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two 64-bit integers."""
    return bin(a ^ b).count("1")


class SimHashDeduplicator:
    """Memory-bounded near-duplicate detector using SimHash fingerprints.

    Args:
        threshold: Maximum Hamming distance to consider two documents as
                   near-duplicates. 3 ≈ 95% similarity.
        maxsize:   LRU capacity in number of documents.
    """

    def __init__(self, threshold: int = 3, maxsize: int = 16_000) -> None:
        self.threshold = threshold
        self.maxsize = maxsize
        self._store: OrderedDict[str, int] = OrderedDict()
        self._stats = {"total": 0, "duplicates": 0}

    def is_duplicate(self, doc_id: str, text: str) -> bool:
        """Return True if *text* is a near-duplicate of any stored document."""
        self._stats["total"] += 1
        fingerprint = compute_simhash(text)

        if doc_id in self._store:
            self._stats["duplicates"] += 1
            return True

        for stored_fp in self._store.values():
            if hamming_distance(fingerprint, stored_fp) <= self.threshold:
                self._stats["duplicates"] += 1
                return True

        self._store[doc_id] = fingerprint
        self._store.move_to_end(doc_id)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)
        return False

    def add(self, doc_id: str, text: str) -> int:
        """Store *text* without checking for duplicates. Returns fingerprint."""
        fingerprint = compute_simhash(text)
        if len(self._store) >= self.maxsize:
            self._store.popitem(last=False)
        self._store[doc_id] = fingerprint
        self._store.move_to_end(doc_id)
        return fingerprint

    def similar_to(self, text: str, *, top_k: int = 5) -> list[tuple[str, int]]:
        """Return top-k most similar stored document ids with their Hamming distances."""
        fingerprint = compute_simhash(text)
        distances = [
            (doc_id, hamming_distance(fingerprint, fp))
            for doc_id, fp in self._store.items()
        ]
        distances.sort(key=lambda x: x[1])
        return distances[:top_k]

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def stats(self) -> dict:
        dup_rate = (
            self._stats["duplicates"] / self._stats["total"]
            if self._stats["total"] > 0
            else 0.0
        )
        return {
            **self._stats,
            "stored": self.size,
            "duplicate_rate": round(dup_rate, 3),
        }

    def clear(self) -> None:
        self._store.clear()
        self._stats = {"total": 0, "duplicates": 0}


_URL_TRACKING = re.compile(
    r"[?&](utm_[^&]+|ref=[^&]+|source=[^&]+|fbclid=[^&]+|gclid=[^&]+)",
    re.I,
)
_URL_TRAILING_SLASH = re.compile(r"/+$")


def normalize_url(url: str) -> str:
    """Return a canonical URL for deduplication purposes."""
    url = url.strip()
    url = url.split("#")[0]
    url = _URL_TRACKING.sub("", url)
    url = url.rstrip("?&")
    if url.count("/") > 2:
        url = _URL_TRAILING_SLASH.sub("", url)
    return url.lower()


_deduplicator: SimHashDeduplicator | None = None


def get_deduplicator() -> SimHashDeduplicator:
    """Return the shared pipeline deduplicator (lazy init)."""
    global _deduplicator
    if _deduplicator is None:
        _deduplicator = SimHashDeduplicator(threshold=3, maxsize=20_000)
        logger.info(
            "SimHash deduplicator initialized (threshold=3, maxsize=20000)"
        )
    return _deduplicator
