"""OpenAI semantic embedding provider."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from backend.interfaces import Embedding


class EmbeddingConfigurationError(ValueError):
    pass


class OpenAIEmbeddingService:
    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._model = model or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        if not self._model.strip():
            raise EmbeddingConfigurationError("OPENAI_EMBEDDING_MODEL cannot be blank")
        if client is None:
            resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
            if not resolved_key:
                raise EmbeddingConfigurationError(
                    "OPENAI_API_KEY is required when MEMORA_EMBEDDING_PROVIDER=openai"
                )
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise EmbeddingConfigurationError(
                    "the 'openai' package is required for OpenAI embeddings"
                ) from exc
            client = OpenAI(api_key=resolved_key)
        self._client = client

    @property
    def model_name(self) -> str:
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        if not texts:
            return ()
        response = self._client.embeddings.create(
            model=self._model, input=list(texts), encoding_format="float"
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(texts):
            raise RuntimeError("OpenAI returned an unexpected number of embeddings")
        return tuple(tuple(float(value) for value in item.embedding) for item in ordered)

    def embed_query(self, text: str) -> Embedding:
        if not text.strip():
            raise ValueError("embedding input cannot be blank")
        return self.embed_documents([text])[0]

