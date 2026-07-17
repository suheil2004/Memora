"""Composition helpers for indexing imported conversations."""

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.interfaces import EmbeddingService, ImportedConversation
from backend.models import User


def index_conversation(
    imported: ImportedConversation,
    *,
    user: User,
    chunker: ConversationChunker,
    embeddings: EmbeddingService,
    store: SQLiteVectorStore,
) -> None:
    store.save_import(user, imported)
    chunks = chunker.chunk(imported)
    vectors = embeddings.embed_documents([chunk.content for chunk in chunks])
    store.upsert(chunks, vectors)

