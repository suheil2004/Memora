"""Application service composing Memora's existing ingestion and RAG pipeline."""

from dataclasses import dataclass
from typing import Any

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import JsonConversationImporter
from backend.ingestion.bulk_import import BulkImportSummary, ChatGPTBulkImportService
from backend.ingestion.chatgpt_export import ChatGPTExportImporter
from backend.interfaces import EmbeddingService, RetrievalResult
from backend.models import User
from backend.rag.context_builder import CompactContextBuilder
from backend.rag.pipeline import index_conversation
from backend.rag.retriever import SemanticMemoryRetriever


@dataclass(frozen=True, slots=True)
class ImportSummary:
    conversation_id: str
    title: str | None
    chunks_indexed: int
    embedding_provider: str
    embedding_model: str


@dataclass(frozen=True, slots=True)
class ContextResponseData:
    query: str
    context: str
    results: tuple[RetrievalResult, ...]


class MemoraService:
    def __init__(
        self,
        *,
        importer: JsonConversationImporter,
        chunker: ConversationChunker,
        embeddings: EmbeddingService,
        store: SQLiteVectorStore,
        context_builder: CompactContextBuilder,
        context_max_chars: int = 6000,
    ) -> None:
        self.importer = importer
        self.chunker = chunker
        self.embeddings = embeddings
        self.store = store
        self.context_builder = context_builder
        self.context_max_chars = context_max_chars
        self.retriever = SemanticMemoryRetriever(embeddings, store)

    def import_conversation(self, payload: dict[str, Any], *, user_id: str) -> ImportSummary:
        imported = self.importer.import_data(payload, user_id=user_id)[0]
        chunks = index_conversation(
            imported,
            user=User(user_id),
            chunker=self.chunker,
            embeddings=self.embeddings,
            store=self.store,
        )
        return ImportSummary(
            conversation_id=imported.conversation.id,
            title=imported.conversation.title,
            chunks_indexed=len(chunks),
            embedding_provider=self.embeddings.provider_name,
            embedding_model=self.embeddings.model_name,
        )

    def retrieve_context(
        self,
        query: str,
        *,
        user_id: str,
        top_k: int,
        min_similarity: float,
        max_context_chars: int | None = None,
    ) -> ContextResponseData:
        results = self.retriever.retrieve(
            query,
            user_id=user_id,
            limit=top_k,
            min_similarity=min_similarity,
        )
        context = self.context_builder.build(
            query,
            results,
            max_chars=max_context_chars or self.context_max_chars,
        )
        return ContextResponseData(query, context, results)

    def import_chatgpt_history(
        self,
        uploads: tuple[tuple[str, bytes], ...],
        *,
        user_id: str,
    ) -> BulkImportSummary:
        return ChatGPTBulkImportService(
            importer=ChatGPTExportImporter(),
            chunker=self.chunker,
            embeddings=self.embeddings,
            store=self.store,
        ).import_uploads(uploads, user_id=user_id)
