"""Deterministic query-aware reranking for semantically eligible chunks."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from backend.interfaces import RetrievalResult


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_COURSE_CODE_PATTERN = re.compile(
    r"(?<![a-z0-9])([a-z]{2,5})([\s-]?)(\d{3})(?![a-z0-9])", re.I
)
_ACADEMIC_TERMS = frozenset({
    "assignment", "class", "course", "exam", "lecture", "note", "pdf",
    "practice", "professor", "question", "document", "file",
})
_COURSE_TASK_TERMS = frozenset({
    "assignment", "exam", "final", "homework", "lecture", "note", "pdf",
    "practice", "professor", "project", "quiz", "report",
})
_STOP_WORDS = {
    "a", "about", "again", "an", "and", "are", "did", "do", "for", "how",
    "i", "in", "is", "it", "me", "my", "of", "on", "tell", "the", "to",
    "was", "what", "where", "who", "with",
}
_ALIASES = {
    "bake": "cook", "baked": "cook", "baking": "cook",
    "cooked": "cook", "cooking": "cook",
    "exercise": "workout", "exercises": "workout", "fitness": "workout",
    "detection": "detect", "detector": "detect", "detecting": "detect",
}


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    result: RetrievalResult
    hybrid_score: float
    content_overlap: float
    title_overlap: float
    entity_match: bool
    entity_mismatch: bool
    academic_overlap: float


class HybridReranker:
    """Blend cosine similarity with query overlap, then diversify conversations.

    Score = 0.75 * cosine + 0.15 * chunk overlap + 0.10 * title overlap
    + 0.30 * exact course-code match - 0.25 * explicit course-code mismatch
    + 0.08 * academic-intent overlap.
    Both overlap values are the fraction of significant normalized query terms
    found in the corresponding candidate field.
    """

    def __init__(
        self,
        *,
        semantic_weight: float = 0.75,
        content_weight: float = 0.15,
        title_weight: float = 0.10,
        entity_match_bonus: float = 0.30,
        entity_mismatch_penalty: float = 0.25,
        academic_intent_bonus: float = 0.08,
        document_intent_bonus: float = 0.12,
    ) -> None:
        if min(semantic_weight, content_weight, title_weight) < 0:
            raise ValueError("reranking weights cannot be negative")
        if abs(semantic_weight + content_weight + title_weight - 1.0) > 1e-9:
            raise ValueError("reranking weights must sum to 1")
        self.semantic_weight = semantic_weight
        self.content_weight = content_weight
        self.title_weight = title_weight
        if min(entity_match_bonus, entity_mismatch_penalty, academic_intent_bonus, document_intent_bonus) < 0:
            raise ValueError("entity reranking adjustments cannot be negative")
        self.entity_match_bonus = entity_match_bonus
        self.entity_mismatch_penalty = entity_mismatch_penalty
        self.academic_intent_bonus = academic_intent_bonus
        self.document_intent_bonus = document_intent_bonus

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalResult],
        *,
        limit: int,
    ) -> tuple[RetrievalResult, ...]:
        if limit < 1 or not candidates:
            return ()
        scored = self.rank_candidates(query, candidates)

        diverse: list[RetrievalResult] = []
        seen_conversations: set[str] = set()
        for ranked in scored:
            candidate = ranked.result
            conversation_key = candidate.conversation_id or candidate.source_id
            if conversation_key in seen_conversations:
                continue
            seen_conversations.add(conversation_key)
            diverse.append(candidate)
            if len(diverse) == limit:
                break
        return tuple(diverse)

    def rank_candidates(
        self, query: str, candidates: Sequence[RetrievalResult]
    ) -> tuple[RankedCandidate, ...]:
        query_terms = significant_terms(query)
        query_entities = extract_course_codes(query)
        query_academic_terms = query_terms & _ACADEMIC_TERMS
        scored = []
        for candidate in candidates:
            content_overlap = _overlap(query_terms, candidate.content)
            title_overlap = _overlap(query_terms, candidate.conversation_title or "")
            candidate_text = f"{candidate.conversation_title or candidate.document_filename or ''}\n{candidate.content}"
            candidate_entities = extract_course_codes(candidate_text) | frozenset(candidate.trusted_entity_codes)
            entity_match = bool(query_entities & candidate_entities)
            entity_mismatch = bool(
                query_entities and candidate_entities and not entity_match
            )
            academic_overlap = _academic_overlap(query_academic_terms, candidate_text)
            document_match = bool(query_academic_terms) and candidate.source_kind == "document"
            scored.append(RankedCandidate(
                result=candidate,
                hybrid_score=(
                    self.semantic_weight * candidate.score
                    + self.content_weight * content_overlap
                    + self.title_weight * title_overlap
                    + self.entity_match_bonus * float(entity_match)
                    - self.entity_mismatch_penalty * float(entity_mismatch)
                    + self.academic_intent_bonus * academic_overlap
                    + self.document_intent_bonus * float(document_match)
                ),
                content_overlap=content_overlap,
                title_overlap=title_overlap,
                entity_match=entity_match,
                entity_mismatch=entity_mismatch,
                academic_overlap=academic_overlap,
            ))
        scored.sort(
            key=lambda item: (
                -item.hybrid_score, -item.result.score, item.result.source_id
            )
        )
        return tuple(scored)


def _overlap(query_terms: frozenset[str], text: str) -> float:
    if not query_terms:
        return 0.0
    return len(query_terms & significant_terms(text)) / len(query_terms)


def _academic_overlap(query_terms: frozenset[str], text: str) -> float:
    if not query_terms:
        return 0.0
    return len(query_terms & significant_terms(text)) / len(query_terms)


def extract_course_codes(text: str) -> frozenset[str]:
    """Return generic academic identifiers in canonical ``DEPT 123`` form."""

    return frozenset(
        f"{department.upper()} {number}"
        for department, separator, number in _COURSE_CODE_PATTERN.findall(text)
        if department.isupper() or separator != " "
    )


def entity_dominant_course_code(query: str) -> str | None:
    """Return one exact course code only for broad entity-browsing queries."""

    codes = extract_course_codes(query)
    if len(codes) != 1:
        return None
    return next(iter(codes)) if not (significant_terms(query) & _COURSE_TASK_TERMS) else None


def significant_terms(text: str) -> frozenset[str]:
    normalized = re.sub(r"\bartificial[\s-]+intelligence\b", "ai", text.lower())
    terms = []
    for raw in _TOKEN_PATTERN.findall(normalized):
        if raw in _STOP_WORDS:
            continue
        if raw in _ALIASES:
            terms.append(_ALIASES[raw])
            continue
        stemmed = _stem(raw)
        terms.append(_ALIASES.get(stemmed, stemmed))
    return frozenset(terms)


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) > len(suffix) + 3:
            return token[: -len(suffix)]
    return token
