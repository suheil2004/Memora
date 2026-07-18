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
