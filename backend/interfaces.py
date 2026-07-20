"""Typed boundaries between Memora domain services and implementations."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, Sequence

from backend.models import (
    AttachmentSource, Conversation, ConversationChunk, DocumentChunk, MemoryBrief, MemoryFact,
    MemoryThread,
    Message, StructuredMemory,
)

Embedding = tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ImportedConversation:
    conversation: Conversation
    messages: tuple[Message, ...]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    content: str
    score: float
    source_kind: str
    source_id: str
    conversation_id: str | None = None
    conversation_title: str | None = None
    user_id: str | None = None
    source_message_ids: tuple[str, ...] = ()
    source_created_at: datetime | None = None
    document_id: str | None = None
    document_filename: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    trusted_entity_codes: tuple[str, ...] = ()
    attachment_sources: tuple[AttachmentSource, ...] = ()


class ConversationImporter(Protocol):
    def import_file(self, path: Path, *, user_id: str) -> Sequence[ImportedConversation]: ...


class EmbeddingService(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Embedding]: ...

    def embed_query(self, text: str) -> Embedding: ...


class VectorStore(Protocol):
    def upsert(
        self,
        chunks: Sequence[ConversationChunk],
        embeddings: Sequence[Embedding],
        *,
        embedding_provider: str,
        embedding_model: str,
    ) -> None: ...

    def search(
        self,
        query_embedding: Embedding,
        *,
        user_id: str,
        limit: int,
        min_similarity: float = 0.0,
        embedding_provider: str,
        embedding_model: str,
    ) -> Sequence[RetrievalResult]: ...

    def delete_conversation(self, conversation_id: str, *, user_id: str) -> None: ...

    def search_course_scope(
        self,
        course_code: str,
        *,
        user_id: str,
        limit: int,
        query_embedding: Embedding | None = None,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
    ) -> Sequence[RetrievalResult]: ...


class MemoryExtractor(Protocol):
    def extract(self, conversation: Conversation, messages: Sequence[Message]) -> Sequence[StructuredMemory]: ...


class MemoryRetriever(Protocol):
    def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        limit: int,
        min_similarity: float = 0.0,
    ) -> Sequence[RetrievalResult]: ...


class MemorySynthesizer(Protocol):
    def synthesize(self, query: str, thread: MemoryThread) -> MemoryBrief: ...


class MemoryFactExtractor(Protocol):
    def extract(self, thread: MemoryThread) -> Sequence[MemoryFact]: ...


class ContextBuilder(Protocol):
    def build(self, query: str, results: Sequence[RetrievalResult], *, max_chars: int) -> str: ...
