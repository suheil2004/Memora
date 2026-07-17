import json
import tempfile
import unittest
from pathlib import Path

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import ConversationImportError, JsonConversationImporter
from backend.models import User
from backend.rag.context_builder import CompactContextBuilder
from backend.rag.local_embeddings import LocalHashEmbeddingService
from backend.rag.pipeline import index_conversation
from backend.rag.retriever import SemanticMemoryRetriever


ROOT = Path(__file__).resolve().parents[1]


class VerticalSliceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SQLiteVectorStore(Path(self.temp_dir.name) / "test.sqlite3")
        self.importer = JsonConversationImporter()
        self.embeddings = LocalHashEmbeddingService(dimensions=128)
        self.chunker = ConversationChunker(max_tokens=80, overlap_tokens=20)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _index(self, filename: str, user: User) -> None:
        imported = self.importer.import_file(ROOT / "samples" / filename, user_id=user.id)[0]
        index_conversation(
            imported,
            user=user,
            chunker=self.chunker,
            embeddings=self.embeddings,
            store=self.store,
        )

    def test_end_to_end_retrieves_drone_context_above_unrelated_context(self) -> None:
        user = User("user-one")
        self._index("drone_detection.json", user)
        self._index("sourdough.json", user)

        results = SemanticMemoryRetriever(self.embeddings, self.store).retrieve(
            "How can I reduce inference latency on my project?",
            user_id=user.id,
            limit=5,
            min_similarity=0.0,
        )

        self.assertEqual(results[0].conversation_id, "conv_drone_001")
        self.assertGreater(results[0].score, results[1].score)
        self.assertEqual(results[0].user_id, user.id)
        self.assertEqual(results[0].source_kind, "chunk")
        self.assertTrue(results[0].source_id)
        self.assertTrue(results[0].source_message_ids)
        self.assertEqual(results[0].conversation_title, "Drone Detection Project")
        context = CompactContextBuilder().build("latency", results[:1], max_chars=500)
        self.assertIn("Drone Detection Project", context)
        self.assertIn("Raspberry Pi 4", context)
        self.assertNotIn("sourdough", context.lower())

    def test_search_is_isolated_by_user_before_ranking(self) -> None:
        owner = User("owner")
        other = User("other")
        self._index("drone_detection.json", owner)
        self._index("sourdough.json", other)

        retriever = SemanticMemoryRetriever(self.embeddings, self.store)
        owner_results = retriever.retrieve("inference CUDA", user_id=owner.id, limit=5)
        other_results = retriever.retrieve("inference CUDA", user_id=other.id, limit=5)

        self.assertEqual({r.conversation_id for r in owner_results}, {"conv_drone_001"})
        self.assertEqual({r.conversation_id for r in other_results}, {"conv_bread_001"})

    def test_invalid_json_has_clear_error(self) -> None:
        path = Path(self.temp_dir.name) / "invalid.json"
        path.write_text('{"conversation_id": "c1", "messages": [}', encoding="utf-8")
        with self.assertRaisesRegex(ConversationImportError, "line .* column"):
            self.importer.import_file(path, user_id="user-one")

    def test_missing_required_field_has_clear_error(self) -> None:
        path = Path(self.temp_dir.name) / "missing.json"
        path.write_text(json.dumps({"conversation_id": "c1", "messages": [{}]}), encoding="utf-8")
        with self.assertRaisesRegex(ConversationImportError, r"messages\[0\]\.role"):
            self.importer.import_file(path, user_id="user-one")

    def test_embeddings_are_deterministic(self) -> None:
        text = "Windows laptop with CUDA runs inference"
        self.assertEqual(self.embeddings.embed_query(text), self.embeddings.embed_query(text))
        self.assertEqual(
            self.embeddings.embed_documents([text])[0], self.embeddings.embed_query(text)
        )

    def test_context_builder_enforces_exact_size_limit(self) -> None:
        user = User("user-one")
        self._index("drone_detection.json", user)
        result = SemanticMemoryRetriever(self.embeddings, self.store).retrieve(
            "CUDA inference", user_id=user.id, limit=1
        )
        for maximum in (5, 40, 100):
            context = CompactContextBuilder().build("CUDA", result, max_chars=maximum)
            self.assertLessEqual(len(context), maximum)

    def test_chunker_preserves_roles_order_and_provenance(self) -> None:
        imported = self.importer.import_file(
            ROOT / "samples" / "drone_detection.json", user_id="user-one"
        )[0]
        chunks = ConversationChunker(max_tokens=15, overlap_tokens=5).chunk(imported)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(chunks[0].content.startswith("User:"))
        self.assertEqual(chunks[0].conversation_id, imported.conversation.id)
        self.assertTrue(chunks[0].message_ids)


if __name__ == "__main__":
    unittest.main()
