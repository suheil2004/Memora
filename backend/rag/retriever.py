"""Query embedding and user-scoped vector retrieval orchestration."""

from backend.interfaces import EmbeddingService, RetrievalResult, VectorStore


class SemanticMemoryRetriever:
    def __init__(self, embeddings: EmbeddingService, vector_store: VectorStore) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store

    def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        limit: int,
        min_similarity: float = 0.0,
    ) -> tuple[RetrievalResult, ...]:
        if not query.strip():
            return ()
        return tuple(
            self.vector_store.search(
                self.embeddings.embed_query(query),
                user_id=user_id,
                limit=limit,
                min_similarity=min_similarity,
                embedding_provider=self.embeddings.provider_name,
                embedding_model=self.embeddings.model_name,
            )
        )
