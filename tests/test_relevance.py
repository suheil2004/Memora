import os
import unittest
from unittest.mock import patch

from backend.rag.local_embeddings import LocalHashEmbeddingService
from backend.rag.relevance import (
    RelevanceConfigurationError,
    minimum_relevance_similarity,
)


class RelevancePolicyTests(unittest.TestCase):
    def test_known_local_spaces_have_calibrated_floors(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                minimum_relevance_similarity(LocalHashEmbeddingService()), 0.06
            )
            self.assertEqual(
                minimum_relevance_similarity(LocalHashEmbeddingService(dimensions=256)),
                0.08,
            )

    def test_semantic_provider_requires_explicit_calibrated_floor(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RelevanceConfigurationError, "must be configured"
            ):
                minimum_relevance_similarity(EmbeddingSpace("openai", "text-embedding-3-small"))

    def test_explicit_floor_applies_to_known_and_unknown_providers(self) -> None:
        with patch.dict(
            os.environ, {"MEMORA_RELEVANCE_MIN_SIMILARITY": "0.17"}, clear=True
        ):
            self.assertEqual(
                minimum_relevance_similarity(
                    EmbeddingSpace("openai", "text-embedding-3-small")
                ),
                0.17,
            )
            self.assertEqual(
                minimum_relevance_similarity(EmbeddingSpace("custom", "model-v1")),
                0.17,
            )

    def test_invalid_explicit_floor_fails_closed(self) -> None:
        for value in ("not-a-number", "1.01", "-1.01"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"MEMORA_RELEVANCE_MIN_SIMILARITY": value}, clear=True
            ):
                with self.assertRaises(RelevanceConfigurationError):
                    minimum_relevance_similarity(EmbeddingSpace("openai", "model"))


class EmbeddingSpace:
    def __init__(self, provider_name: str, model_name: str) -> None:
        self.provider_name = provider_name
        self.model_name = model_name

    def embed_query(self, text: str):
        raise NotImplementedError

    def embed_documents(self, texts):
        raise NotImplementedError


if __name__ == "__main__":
    unittest.main()
