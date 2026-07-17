"""Environment-based embedding-provider composition."""

import os

from backend.interfaces import EmbeddingService
from backend.rag.local_embeddings import LocalHashEmbeddingService
from backend.rag.openai_embeddings import EmbeddingConfigurationError, OpenAIEmbeddingService


def create_embedding_service(provider: str | None = None) -> EmbeddingService:
    selected = (provider or os.environ.get("MEMORA_EMBEDDING_PROVIDER", "local")).strip().lower()
    if selected == "local":
        return LocalHashEmbeddingService()
    if selected == "openai":
        return OpenAIEmbeddingService()
    raise EmbeddingConfigurationError(
        f"unsupported embedding provider '{selected}'; expected 'local' or 'openai'"
    )
