"""Duplicate-aware bulk indexing for normalized ChatGPT exports."""

from dataclasses import dataclass
from time import monotonic

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chatgpt_export import ChatGPTExportImporter, normalized_fingerprint
from backend.ingestion.chunker import ConversationChunker
from backend.interfaces import EmbeddingService
from backend.models import User
from backend.rag.pipeline import index_conversation


@dataclass(frozen=True, slots=True)
class BulkImportSummary:
    conversations_found: int
    conversations_imported: int
    conversations_skipped: int
    messages_imported: int
    chunks_indexed: int
    embedding_provider: str
    embedding_model: str
    duration_seconds: float
    errors: tuple[str, ...]


class ChatGPTBulkImportService:
    def __init__(
        self,
        *,
        importer: ChatGPTExportImporter,
        chunker: ConversationChunker,
        embeddings: EmbeddingService,
        store: SQLiteVectorStore,
    ) -> None:
        self.importer = importer
        self.chunker = chunker
        self.embeddings = embeddings
        self.store = store

    def import_uploads(
        self,
        uploads: tuple[tuple[str, bytes], ...],
        *,
        user_id: str,
    ) -> BulkImportSummary:
        started = monotonic()
        batch = self.importer.import_uploads(uploads, user_id=user_id)
        imported_count = messages = chunks = 0
        skipped = batch.conversations_found - len(batch.conversations)
        errors = [f"{error.source}: {error.message}" for error in batch.errors]
        user = User(user_id)
        for imported in batch.conversations:
            fingerprint = normalized_fingerprint(imported)
            existing = self.store.get_import_fingerprint(imported.conversation.id, user_id=user_id)
            if existing == fingerprint:
                skipped += 1
                continue
            try:
                indexed = index_conversation(
                    imported,
                    user=user,
                    chunker=self.chunker,
                    embeddings=self.embeddings,
                    store=self.store,
                    import_fingerprint=fingerprint,
                )
                imported_count += 1
                messages += len(imported.messages)
                chunks += len(indexed)
            except Exception:
                skipped += 1
                errors.append(f"conversation {imported.conversation.id}: indexing failed")
        return BulkImportSummary(
            conversations_found=batch.conversations_found,
            conversations_imported=imported_count,
            conversations_skipped=skipped,
            messages_imported=messages,
            chunks_indexed=chunks,
            embedding_provider=self.embeddings.provider_name,
            embedding_model=self.embeddings.model_name,
            duration_seconds=round(monotonic() - started, 3),
            errors=tuple(errors),
        )
