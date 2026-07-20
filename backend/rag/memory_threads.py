"""Conservative subject- and goal-aware grouping of reranked evidence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from backend.interfaces import RetrievalResult
from backend.models import DocumentSource, MemoryThread
from backend.rag.reranker import RankedCandidate, extract_course_codes, significant_terms


_BROAD_TERMS = {
    "ai", "chat", "conversation", "discussion", "drone", "fitness", "memory",
    "plan", "project", "school", "thread", "workout",
}
_VERSION_MARKERS = ("old", "previous", "original", "updated", "revised", "new", "latest")
_SUBJECT_PATTERNS = (
    ("girlfriend", re.compile(r"\bgirlfriend(?:'s)?\b", re.I)),
    ("boyfriend", re.compile(r"\bboyfriend(?:'s)?\b", re.I)),
    ("wife", re.compile(r"\bwife(?:'s)?\b", re.I)),
    ("husband", re.compile(r"\bhusband(?:'s)?\b", re.I)),
    ("partner", re.compile(r"\bpartner(?:'s)?\b", re.I)),
    ("friend", re.compile(r"\bfriend(?:'s)?\b", re.I)),
    ("team", re.compile(r"\b(?:our|my) team\b|\bteam's\b", re.I)),
)
_SELF_PATTERN = re.compile(r"\b(?:i|me|my|mine|myself)\b", re.I)


@dataclass(slots=True)
class _ThreadDraft:
    subject: str
    signature: frozenset[str]
    version_markers: frozenset[str]
    course_codes: frozenset[str]
    academic_focus: str | None
    evidence: list[RankedCandidate] = field(default_factory=list)


class MemoryThreadGrouper:
    """Prefer separate threads; merge cross-conversation evidence only when strong."""

    def group(
        self,
        query: str,
        candidates: tuple[RankedCandidate, ...],
        *,
        limit: int = 5,
    ) -> tuple[tuple[MemoryThread, RetrievalResult], ...]:
        if limit < 1 or not candidates:
            return ()
        drafts: list[_ThreadDraft] = []
        for candidate in candidates:
            subject = _subject(candidate.result.content)
            signature = _goal_signature(candidate.result)
            markers = _version_markers(candidate.result)
            course_codes = _course_codes(candidate.result)
            academic_focus = _academic_focus(candidate.result)
            matching = next(
                (
                    draft for draft in drafts
                    if _same_thread(
                        draft, candidate, subject, signature, markers,
                        course_codes, academic_focus,
                    )
                ),
                None,
            )
            if matching is None:
                drafts.append(_ThreadDraft(
                    subject, signature, markers, course_codes, academic_focus, [candidate]
                ))
            else:
                matching.evidence.append(candidate)
                matching.signature = matching.signature | signature
                matching.version_markers = matching.version_markers | markers

        built = [self._build_thread(query, draft) for draft in drafts]
        built.sort(key=lambda item: (
            -item[0].strongest_hybrid_score,
            -item[0].strongest_cosine_score,
            item[0].thread_id,
        ))
        return tuple(built[:limit])

    def _build_thread(
        self, query: str, draft: _ThreadDraft
    ) -> tuple[MemoryThread, RetrievalResult]:
        evidence = sorted(
            draft.evidence,
            key=lambda item: (-item.hybrid_score, -item.result.score, item.result.source_id),
        )
        representative = evidence[0].result
        chunk_ids = _unique(item.result.source_id for item in evidence)
        source_conversations: dict[str, str] = {}
        for item in evidence:
            if item.result.conversation_id:
                source_conversations.setdefault(
                    item.result.conversation_id,
                    item.result.conversation_title or "Previous conversation",
                )
        conversation_ids = tuple(source_conversations)
        message_ids = _unique(
            message_id for item in evidence for message_id in item.result.source_message_ids
        )
        source_titles = tuple(source_conversations.values())
        timestamps = tuple(sorted(
            [timestamp for timestamp in (
                item.result.source_created_at for item in evidence
            ) if timestamp is not None],
            key=lambda value: value.isoformat(),
        ))
        topic_terms = significant_terms(query) & set().union(
            *(significant_terms(item.result.content) for item in evidence)
        )
        topic = " ".join(sorted(topic_terms)) or "unknown"
        context_terms = sorted(draft.signature)[:6]
        goal_or_context = " ".join(context_terms) or "unknown"
        document_sources = tuple(dict.fromkeys(
            DocumentSource(
                item.result.document_id or "",
                item.result.document_filename or "Document",
                item.result.page_start or 1,
                item.result.page_end or item.result.page_start or 1,
                item.result.conversation_id,
            )
            for item in evidence if item.result.document_id
        ))
        attachment_sources = tuple(dict.fromkeys(
            source for item in evidence for source in item.result.attachment_sources
        ))
        title = (
            representative.conversation_title or representative.document_filename
            or "Previous conversation"
        )
        digest = hashlib.sha256("\0".join(sorted(chunk_ids)).encode()).hexdigest()[:16]
        thread = MemoryThread(
            thread_id=f"thread-{digest}",
            title=title,
            subject=draft.subject,
            topic=topic,
            goal_or_context=goal_or_context,
            source_titles=source_titles,
            source_conversation_ids=conversation_ids,
            source_chunk_ids=chunk_ids,
            source_message_ids=message_ids,
            strongest_cosine_score=max(item.result.score for item in evidence),
            strongest_hybrid_score=max(item.hybrid_score for item in evidence),
            supporting_chunks=tuple(item.result.content for item in evidence),
            source_timestamps=timestamps,
            document_sources=document_sources,
            attachment_sources=attachment_sources,
        )
        return thread, representative


def _same_thread(
    draft: _ThreadDraft,
    candidate: RankedCandidate,
    subject: str,
    signature: frozenset[str],
    markers: frozenset[str],
    course_codes: frozenset[str],
    academic_focus: str | None,
) -> bool:
    conversation_id = candidate.result.conversation_id or candidate.result.source_id
    same_conversation = any(
        (item.result.conversation_id or item.result.source_id) == conversation_id
        for item in draft.evidence
    )
    if draft.subject != subject:
        return False
    if draft.course_codes and course_codes:
        if not draft.course_codes & course_codes:
            return False
        if draft.academic_focus and academic_focus and draft.academic_focus != academic_focus:
            return False
    if draft.version_markers and markers and draft.version_markers != markers:
        return False
    shared = draft.signature & signature
    same_course = bool(draft.course_codes & course_codes)
    if same_course and draft.academic_focus and draft.academic_focus == academic_focus:
        return True
    if same_conversation:
        return bool(shared)
    if subject == "unknown":
        return False
    if len(shared) < 2:
        return False
    union = draft.signature | signature
    containment = len(shared) / min(len(draft.signature), len(signature))
    return len(shared) / len(union) >= 0.25 or containment >= 0.50


def _subject(text: str) -> str:
    for subject, pattern in _SUBJECT_PATTERNS:
        if pattern.search(text):
            return subject
    return "user" if _SELF_PATTERN.search(text) else "unknown"


def _goal_signature(result: RetrievalResult) -> frozenset[str]:
    terms = significant_terms(
        f"{result.conversation_title or result.document_filename or ''}\n{result.content}"
    )
    entity_parts = {
        part.lower() for code in _course_codes(result) for part in code.split()
    }
    return frozenset(terms - _BROAD_TERMS - set(_VERSION_MARKERS) - entity_parts)


def _course_codes(result: RetrievalResult) -> frozenset[str]:
    return extract_course_codes(
        f"{result.conversation_title or result.document_filename or ''}\n{result.content}"
    ) | frozenset(result.trusted_entity_codes)


def _academic_focus(result: RetrievalResult) -> str | None:
    terms = significant_terms(f"{result.conversation_title or ''}\n{result.content}")
    if "exam" in terms and "practice" in terms:
        return "practice_exam"
    if "exam" in terms and "final" in terms:
        return "final_exam"
    if "assignment" in terms:
        return "assignment"
    if "project" in terms:
        return "project"
    if "homework" in terms or "quiz" in terms:
        return "coursework"
    if terms & {"lecture", "note", "pdf"}:
        return "course_materials"
    if terms & {"class", "course", "exam", "professor"}:
        return "course_overview"
    return None


def _version_markers(result: RetrievalResult) -> frozenset[str]:
    text = f"{result.conversation_title or ''}\n{result.content}".lower()
    return frozenset(
        marker for marker in _VERSION_MARKERS
        if re.search(rf"\b{re.escape(marker)}\b", text)
    )


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
