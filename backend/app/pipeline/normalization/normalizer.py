"""Text and URL normalization used by dedup and tag matching."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "igshid",
    "si",
    "feature",
    "ref_src",
    "ref_url",
    "s",
    "_r",
}

HASHTAG_RE = re.compile(r"#([\w一-鿿]+)", re.UNICODE)
NON_WORD_RE = re.compile(r"[^\w\s#@+.-]", re.UNICODE)
SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """NFKC + lowercase + punctuation collapse. Deterministic and fast."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = NON_WORD_RE.sub(" ", normalized)
    return SPACE_RE.sub(" ", normalized).strip()


def tokenize(text: str) -> list[str]:
    return [t for t in normalize_text(text).split() if len(t) > 1]


def extract_hashtags(text: str) -> list[str]:
    seen: list[str] = []
    for tag in HASHTAG_RE.findall(text or ""):
        clean = normalize_text(tag)
        if clean and clean not in seen:
            seen.append(clean)
    return seen


def canonicalize_url(url: str) -> str:
    """Strip tracking params and trailing slashes so URLs dedupe reliably."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, "", urlencode(query), "")
    )


def simhash(text: str, bits: int = 64) -> int:
    """Character-3-gram simhash — cheap near-duplicate detection."""
    tokens = tokenize(text)
    if not tokens:
        return 0
    grams: list[str] = []
    for token in tokens:
        padded = f"  {token} "
        grams.extend(padded[i : i + 3] for i in range(len(padded) - 2))
    if not grams:
        return 0

    vector = [0] * bits
    for gram in grams:
        digest = int.from_bytes(
            hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest(), "big"
        )
        for i in range(bits):
            vector[i] += 1 if digest >> i & 1 else -1

    value = 0
    for i in range(bits):
        if vector[i] > 0:
            value |= 1 << i
    return value


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def similarity(a: int, b: int, bits: int = 64) -> float:
    if not a or not b:
        return 0.0
    return 1.0 - (hamming(a, b) / bits)


def slugify(text: str, max_length: int = 120) -> str:
    text = normalize_text(text).replace(" ", "-")
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return (text or "signal")[:max_length]


def fingerprint(source_id: str, external_id: str) -> str:
    raw = f"{source_id}:{external_id}".encode()
    return hashlib.sha256(raw).hexdigest()[:64]


def content_fingerprint(title: str, description: str = "") -> str:
    raw = f"{normalize_text(title)}|{normalize_text(description)[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]