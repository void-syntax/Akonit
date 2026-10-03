"""Tag matching without any LLM.

Strategy order (safe -> fuzzy): exact hashtag, alias phrase, keyword phrase,
then token-set fuzzy above the configured threshold. The TagMatcher interface
is abstract so an embedding-based matcher can be added later without touching
any caller.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.core.config import settings
from app.pipeline.normalization.normalizer import (
    extract_hashtags,
    normalize_text,
    tokenize,
)


@dataclass
class TagMatch:
    slug: str
    matched_by: str
    score: float


@dataclass
class MatchDocument:
    """Everything the matcher may look at."""

    title: str = ""
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    category: str | None = None
    source_metadata: dict = field(default_factory=dict)
    url: str = ""

    @property
    def text(self) -> str:
        parts = [self.title, self.description, " ".join(self.hashtags)]
        if self.category:
            parts.append(self.category)
        if self.url:
            parts.append(self.url.replace("-", " ").replace("/", " "))
        return normalize_text(" ".join(p for p in parts if p))

    @property
    def tokens(self) -> set[str]:
        return set(tokenize(self.title) + tokenize(self.description))


class TagMatcher(abc.ABC):
    """Interface so an embeddings/ML implementation can drop in later."""

    @abc.abstractmethod
    def match(self, document: MatchDocument) -> list[TagMatch]:
        ...


class KeywordTagMatcher(TagMatcher):
    """Deterministic matcher used by the MVP (no network, no model)."""

    def __init__(
        self,
        keywords: dict[str, list[str]],
        aliases: dict[str, list[str]] | None = None,
    ) -> None:
        self.keywords = {
            k: [normalize_text(v) for v in vals] for k, vals in keywords.items()
        }
        self.aliases = {
            k: [normalize_text(v) for v in vals]
            for k, vals in (aliases or {}).items()
        }

    def match(self, document: MatchDocument) -> list[TagMatch]:
        text = document.text
        tokens = document.tokens
        doc_hashtags = {normalize_text(h).lstrip("#") for h in document.hashtags}
        doc_hashtags |= set(extract_hashtags(document.title))
        matches: dict[str, TagMatch] = {}

        for table, strength in ((self.aliases, 1.0), (self.keywords, 1.0)):
            for slug, terms in table.items():
                for term in terms:
                    if not term:
                        continue
                    if term in doc_hashtags or term.replace(" ", "_") in doc_hashtags:
                        self._keep(matches, slug, "hashtag", strength)
                        break

        for slug, phrases in self.aliases.items():
            if any(p and p in text for p in phrases):
                self._keep(matches, slug, "alias", 0.9)

        for slug, terms in self.keywords.items():
            for term in terms:
                if not term:
                    continue
                if " " in term:
                    if term in text:
                        self._keep(matches, slug, "keyword", 0.85)
                        break
                elif term in tokens:
                    self._keep(matches, slug, "keyword", 0.8)
                    break

        for slug, terms in self.keywords.items():
            if slug in matches:
                continue
            for term in terms:
                if not term or " " in term or len(term) < 5:
                    continue
                for token in tokens:
                    score = fuzz.token_set_ratio(term, token) / 100.0
                    if score >= settings.fuzzy_match_threshold:
                        self._keep(matches, slug, "fuzzy", round(score, 3))
                        break
                if slug in matches:
                    break

        return sorted(matches.values(), key=lambda m: m.score, reverse=True)

    @staticmethod
    def _keep(
        store: dict[str, TagMatch], slug: str, matched_by: str, score: float
    ) -> None:
        current = store.get(slug)
        if current is None or score > current.score:
            store[slug] = TagMatch(slug=slug, matched_by=matched_by, score=score)


class CustomTagMatcher:
    """User-defined tags: keywords, hashtags, excludes, country and source scope."""

    def __init__(self, custom_tags: list[dict]) -> None:
        self.custom_tags = custom_tags

    def match(self, document: MatchDocument) -> list[TagMatch]:
        text = document.text
        tokens = document.tokens
        doc_hashtags = {normalize_text(h).lstrip("#") for h in document.hashtags}
        matches: list[TagMatch] = []

        for tag in self.custom_tags:
            if not tag.get("is_active", True):
                continue

            excludes = [normalize_text(e) for e in (tag.get("excludes") or [])]
            if any(ex and ex in text for ex in excludes):
                continue

            scopes = tag.get("country_codes") or []
            if scopes and document.source_metadata.get("country_code") not in scopes:
                continue
            source_scopes = tag.get("source_ids") or []
            if (
                source_scopes
                and document.source_metadata.get("source_id") not in source_scopes
            ):
                continue

            matched_by = None
            for hashtag in tag.get("hashtags") or []:
                clean = normalize_text(hashtag).lstrip("#")
                if clean and (clean in doc_hashtags or clean in text):
                    matched_by = "custom_hashtag"
                    break

            if matched_by is None:
                for keyword in tag.get("keywords") or []:
                    clean = normalize_text(keyword)
                    if not clean:
                        continue
                    if clean in text or (" " not in clean and clean in tokens):
                        matched_by = "custom_keyword"
                        break

            if matched_by:
                matches.append(
                    TagMatch(
                        slug=f"custom:{tag['slug']}",
                        matched_by=matched_by,
                        score=1.0,
                    )
                )
        return matches


def build_default_matcher() -> KeywordTagMatcher:
    from app.seed.tag_taxonomy import TAG_ALIASES, TAG_KEYWORDS

    return KeywordTagMatcher(TAG_KEYWORDS, TAG_ALIASES)
    def _keep(
        store: dict[str, TagMatch], slug: str, matched_by: str, score: float
    ) -> None:
        current = store.get(slug)
        if current is None or score > current.score:
            store[slug] = TagMatch(slug=slug, matched_by=matched_by, score=score)
    def match(self, document: MatchDocument) -> list[TagMatch]:
        ...