"""Framework-independent core data models for Memora."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MemoryCategory(StrEnum):
    PERSONAL_PROJECT = "personal_project"
    ACADEMIC = "academic"
    PROFESSIONAL = "professional"
    PREFERENCE = "preference"
    PERSONAL_CONTEXT = "personal_context"
    OTHER = "other"


class MemoryFactType(StrEnum):
    FACT = "fact"
    DECISION = "decision"
    GOAL = "goal"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    RESULT = "result"
    STATUS = "status"
    PROBLEM = "problem"
    SOLUTION = "solution"
    CORRECTION = "correction"
    OPEN_LOOP = "open_loop"


@dataclass(frozen=True, slots=True)
class User:
    id: str
    created_at: datetime = field(default_factory=utc_now)
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class Message:
    id: str
    conversation_id: str
    user_id: str
    role: MessageRole
    content: str
    ordinal: int
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("message content cannot be blank")
        if self.ordinal < 0:
            raise ValueError("message ordinal cannot be negative")


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    user_id: str
    source: str
    title: str | None = None
    created_at: datetime | None = None
    imported_at: datetime = field(default_factory=utc_now)
    external_id: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConversationChunk:
    id: str
    conversation_id: str
    user_id: str
    content: str
    ordinal: int
    message_ids: tuple[str, ...]
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("chunk content cannot be blank")
        if self.ordinal < 0:
            raise ValueError("chunk ordinal cannot be negative")
        if not self.message_ids:
            raise ValueError("chunk must reference at least one message")


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    user_id: str
    filename: str
    content_sha256: str
    parent_conversation_id: str | None
    page_count: int
    extraction_status: str = "indexed"
    imported_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    id: str
    document_id: str
    user_id: str
    filename: str
    parent_conversation_id: str | None
    page_start: int
    page_end: int
    content: str
    ordinal: int
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class DocumentSource:
    document_id: str
    filename: str
    page_start: int
    page_end: int
    parent_conversation_id: str | None = None


class BinaryResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    METADATA_ONLY = "metadata_only"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class Attachment:
    id: str
    user_id: str
    conversation_id: str
    message_id: str
    original_filename: str
    mime_type: str | None
    size_bytes: int | None
    library_file_id: str | None
    document_id: str | None
    binary_resolution_status: BinaryResolutionStatus
    imported_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class AttachmentSource:
    attachment_id: str
    filename: str
    mime_type: str | None
    conversation_id: str
    message_id: str
    binary_resolution_status: BinaryResolutionStatus


@dataclass(frozen=True, slots=True)
class StructuredMemory:
    id: str
    user_id: str
    content: str
    category: MemoryCategory
    source_conversation_ids: tuple[str, ...]
    source_message_ids: tuple[str, ...] = ()
    confidence: float = 1.0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("structured memory content cannot be blank")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.source_conversation_ids:
            raise ValueError("structured memory must retain source provenance")


@dataclass(frozen=True, slots=True)
class MemoryThread:
    """A coherent retrieved topic/plan backed by explicit historical evidence."""

    thread_id: str
    title: str
    subject: str
    topic: str
    goal_or_context: str
    source_titles: tuple[str, ...]
    source_conversation_ids: tuple[str, ...]
    source_chunk_ids: tuple[str, ...]
    source_message_ids: tuple[str, ...]
    strongest_cosine_score: float
    strongest_hybrid_score: float
    supporting_chunks: tuple[str, ...]
    source_timestamps: tuple[datetime, ...] = ()
    document_sources: tuple[DocumentSource, ...] = ()
    attachment_sources: tuple[AttachmentSource, ...] = ()

    def __post_init__(self) -> None:
        if not self.thread_id or not self.title.strip():
            raise ValueError("memory thread identity and title are required")
        if not self.source_chunk_ids or not (
            self.source_conversation_ids or self.document_sources or self.attachment_sources
        ):
            raise ValueError("memory thread must retain source provenance")
        if not self.supporting_chunks:
            raise ValueError("memory thread must retain supporting evidence")


@dataclass(frozen=True, slots=True)
class MemoryFact:
    """A concise, salient claim derived from one bounded MemoryThread."""

    fact_id: str
    fact_type: MemoryFactType
    text: str
    subject: str
    salience: float
    specificity: float
    source_conversation_ids: tuple[str, ...]
    source_message_ids: tuple[str, ...]
    source_document_ids: tuple[str, ...]
    source_chunk_ids: tuple[str, ...]
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if not self.fact_id or not self.text.strip():
            raise ValueError("memory fact identity and text are required")
        if not 0.0 <= self.salience <= 1.0:
            raise ValueError("memory fact salience must be between 0 and 1")
        if not 0.0 <= self.specificity <= 1.0:
            raise ValueError("memory fact specificity must be between 0 and 1")
        if not self.source_chunk_ids:
            raise ValueError("memory fact must retain trusted chunk provenance")


@dataclass(frozen=True, slots=True)
class MemoryBrief:
    """Concise synthesis of exactly one MemoryThread with trusted provenance."""

    thread_id: str
    title: str
    subject: str
    summary: str
    key_details: tuple[str, ...]
    sources: tuple[str, ...]
    source_conversation_ids: tuple[str, ...]
    source_chunk_ids: tuple[str, ...]
    source_message_ids: tuple[str, ...]
    used_fallback: bool = False
    document_sources: tuple[DocumentSource, ...] = ()
    attachment_sources: tuple[AttachmentSource, ...] = ()
    latest_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if not self.thread_id or not self.title.strip() or not self.summary.strip():
            raise ValueError("memory brief identity, title, and summary are required")
        if not 1 <= len(self.key_details) <= 5:
            raise ValueError("memory brief requires one to five key details")
        if not self.source_chunk_ids or not (
            self.sources or self.document_sources or self.attachment_sources
        ):
            raise ValueError("memory brief must retain trusted provenance")
