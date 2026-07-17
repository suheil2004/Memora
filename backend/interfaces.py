"""Typed boundaries between Memora domain services and implementations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from backend.models import Conversation, ConversationChunk, Message, StructuredMemory

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


class ContextBuilder(Protocol):
    def build(self, query: str, results: Sequence[RetrievalResult], *, max_chars: int) -> str: ...
