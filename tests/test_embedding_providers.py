import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.database.sqlite_store import IncompatibleEmbeddingError, SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import JsonConversationImporter
from backend.models import User
from backend.rag.local_embeddings import LocalHashEmbeddingService
from backend.rag.openai_embeddings import EmbeddingConfigurationError, OpenAIEmbeddingService
from backend.rag.pipeline import index_conversation
from backend.rag.provider import create_embedding_service
from backend.rag.retriever import SemanticMemoryRetriever


ROOT = Path(__file__).resolve().parents[1]


class FakeEmbeddingsResource:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        data = [
            SimpleNamespace(index=index, embedding=[float(index), 0.5, 1.0])
            for index, _text in enumerate(kwargs["input"])
        ]
        return SimpleNamespace(data=list(reversed(data)))


class EmbeddingProviderTests(unittest.TestCase):
    def test_provider_selection_defaults_to_local(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            service = create_embedding_service()
        self.assertEqual(service.provider_name, "local")

    def test_provider_selection_rejects_unknown_provider(self) -> None:
        with self.assertRaisesRegex(EmbeddingConfigurationError, "unsupported"):
            create_embedding_service("mystery")

    def test_openai_provider_requires_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(EmbeddingConfigurationError, "OPENAI_API_KEY"):
                OpenAIEmbeddingService()

    def test_openai_provider_batches_and_restores_response_order(self) -> None:
        resource = FakeEmbeddingsResource()
        client = SimpleNamespace(embeddings=resource)
        service = OpenAIEmbeddingService(client=client, model="test-model")

        vectors = service.embed_documents(["first", "second"])

        self.assertEqual(vectors, ((0.0, 0.5, 1.0), (1.0, 0.5, 1.0)))
        self.assertEqual(len(resource.calls), 1)
        self.assertEqual(resource.calls[0]["input"], ["first", "second"])
        self.assertEqual(resource.calls[0]["model"], "test-model")

    def test_embedding_metadata_is_persisted_and_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "metadata.sqlite3"
            store = SQLiteVectorStore(database)
            user = User("metadata-user")
            imported = JsonConversationImporter().import_file(
                ROOT / "samples" / "drone_detection.json", user_id=user.id
            )[0]
            indexed_embeddings = LocalHashEmbeddingService(dimensions=128)
            index_conversation(
                imported,
                user=user,
                chunker=ConversationChunker(),
                embeddings=indexed_embeddings,
                store=store,
            )

            with closing(sqlite3.connect(database)) as db:
                metadata = db.execute(
                    "SELECT DISTINCT embedding_provider, embedding_model FROM chunks"
                ).fetchone()
            self.assertEqual(metadata, ("local", "feature-hash-v1-128"))

            incompatible = LocalHashEmbeddingService(dimensions=256)
            with self.assertRaisesRegex(IncompatibleEmbeddingError, "re-index"):
                SemanticMemoryRetriever(incompatible, store).retrieve(
                    "camera", user_id=user.id, limit=3
                )

    def test_deterministic_provider_still_functions(self) -> None:
        service = LocalHashEmbeddingService()
        self.assertEqual(service.embed_query("same text"), service.embed_query("same text"))


if __name__ == "__main__":
    unittest.main()
