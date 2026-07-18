import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.service import MemoraService
from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import JsonConversationImporter
from backend.rag.context_builder import CompactContextBuilder
from backend.rag.local_embeddings import LocalHashEmbeddingService
from backend.rag.openai_embeddings import EmbeddingConfigurationError


ROOT = Path(__file__).resolve().parents[1]


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = MemoraService(
            importer=JsonConversationImporter(),
            chunker=ConversationChunker(max_tokens=80, overlap_tokens=20),
            embeddings=LocalHashEmbeddingService(dimensions=256),
            store=SQLiteVectorStore(Path(self.temp_dir.name) / "api.sqlite3"),
            context_builder=CompactContextBuilder(),
            context_max_chars=1000,
        )
        self.client = TestClient(create_app(service_factory=lambda: self.service))

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def _conversation(self, user_id: str = "demo-user") -> dict:
        payload = json.loads((ROOT / "samples" / "drone_detection.json").read_text())
        return {"user_id": user_id, **payload}

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "memora"})

    def test_import_and_retrieve_with_provenance(self) -> None:
        imported = self.client.post(
            "/api/v1/conversations/import", json=self._conversation()
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["conversation_id"], "conv_drone_001")
        self.assertGreater(imported.json()["chunks_indexed"], 0)
        self.assertEqual(imported.json()["embedding_provider"], "local")

        response = self.client.post(
            "/api/v1/context/retrieve",
            json={
                "user_id": "demo-user",
                "query": "Where was I running detection inference?",
                "top_k": 5,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("Drone Detection Project", body["context"])
        result = body["results"][0]
        self.assertEqual(result["user_id"], "demo-user")
        self.assertEqual(result["conversation_id"], "conv_drone_001")
        self.assertEqual(result["conversation_title"], "Drone Detection Project")
        self.assertTrue(result["chunk_id"])
        self.assertTrue(result["source_message_ids"])
        self.assertIsInstance(result["score"], float)

    def test_retrieval_is_user_isolated(self) -> None:
        self.client.post("/api/v1/conversations/import", json=self._conversation("owner"))
        response = self.client.post(
            "/api/v1/context/retrieve",
            json={"user_id": "other-user", "query": "CUDA inference", "top_k": 5},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        self.assertEqual(response.json()["context"], "")

    def test_invalid_request_and_empty_query_return_validation_errors(self) -> None:
        invalid_import = self.client.post(
            "/api/v1/conversations/import",
            json={"user_id": "u1", "conversation_id": "c1", "messages": []},
        )
        empty_query = self.client.post(
            "/api/v1/context/retrieve",
            json={"user_id": "u1", "query": "   "},
        )
        missing_user = self.client.post(
            "/api/v1/context/retrieve", json={"query": "hello"}
        )
        self.assertEqual(invalid_import.status_code, 422)
        self.assertEqual(empty_query.status_code, 422)
        self.assertEqual(missing_user.status_code, 422)

    def test_embedding_configuration_error_is_sanitized_http_error(self) -> None:
        def unavailable() -> MemoraService:
            raise EmbeddingConfigurationError("OPENAI_API_KEY is required")

        with TestClient(create_app(service_factory=unavailable)) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            response = client.post(
                "/api/v1/context/retrieve",
                json={"user_id": "u1", "query": "hello"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "OPENAI_API_KEY is required"})

    def test_chatgpt_export_multipart_upload_and_duplicate_summary(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "chatgpt" / "conversations.json"
        first = self.client.post(
            "/api/v1/import/chatgpt",
            data={"user_id": "demo-user"},
            files=[("files", ("conversations.json", fixture.read_bytes(), "application/json"))],
        )
        self.assertEqual(first.status_code, 200, first.text)
        summary = first.json()
        self.assertEqual(summary["conversations_found"], 4)
        self.assertEqual(summary["conversations_imported"], 3)
        self.assertEqual(summary["conversations_skipped"], 1)
        self.assertEqual(summary["embedding_provider"], "local")
        self.assertNotIn("embedding", summary)

        second = self.client.post(
            "/api/v1/import/chatgpt",
            data={"user_id": "demo-user"},
            files=[("files", ("conversations.json", fixture.read_bytes(), "application/json"))],
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["conversations_imported"], 0)

    def test_chatgpt_upload_requires_user_and_file(self) -> None:
        missing_user = self.client.post(
            "/api/v1/import/chatgpt",
            files=[("files", ("conversations.json", b"[]", "application/json"))],
        )
        missing_file = self.client.post(
            "/api/v1/import/chatgpt", data={"user_id": "demo-user"}
        )
        self.assertEqual(missing_user.status_code, 422)
        self.assertEqual(missing_file.status_code, 422)


if __name__ == "__main__":
    unittest.main()
