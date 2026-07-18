"""Composition helpers for indexing imported conversations."""

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.interfaces import EmbeddingService, ImportedConversation
from backend.models import ConversationChunk, User


def index_conversation(
    imported: ImportedConversation,
    *,
    user: User,
    chunker: ConversationChunker,
    embeddings: EmbeddingService,
    store: SQLiteVectorStore,
    import_fingerprint: str | None = None,
) -> tuple[ConversationChunk, ...]:
    store.save_import(user, imported, import_fingerprint=import_fingerprint)
    chunks = chunker.chunk(imported)
    vectors = embeddings.embed_documents([chunk.content for chunk in chunks])
    store.upsert(
        chunks,
        vectors,
        embedding_provider=embeddings.provider_name,
        embedding_model=embeddings.model_name,
    )
    return chunks
