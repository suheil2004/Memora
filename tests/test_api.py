import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.security import LocalSecurityConfig
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
            embeddings=CountingLocalEmbeddingService(),
            store=SQLiteVectorStore(Path(self.temp_dir.name) / "api.sqlite3"),
            context_builder=CompactContextBuilder(),
            context_max_chars=1000,
        )
        self.token = "synthetic-test-token-000000000000"
        self.security = LocalSecurityConfig(token=self.token, user_id="demo-user")
        self.client = TestClient(create_app(
            service_factory=lambda: self.service,
            security_config=self.security,
        ))
        self.client.headers.update({"Authorization": f"Bearer {self.token}"})

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def _conversation(self) -> dict:
        payload = json.loads((ROOT / "samples" / "drone_detection.json").read_text())
        return payload

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "memora"})

    def test_cors_preflight_allows_authorization_for_configured_origin(self) -> None:
        response = self.client.options(
            "/api/v1/context/retrieve",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        allowed = response.headers["access-control-allow-headers"].lower()
        self.assertIn("authorization", allowed)
        self.assertIn("content-type", allowed)

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
        imported = self.client.post("/api/v1/conversations/import", json=self._conversation())
        self.assertEqual(imported.status_code, 200)
        response = self.client.post(
            "/api/v1/context/retrieve",
            json={"user_id": "user-b", "query": "CUDA inference", "top_k": 5},
        )
        self.assertEqual(response.status_code, 422)

        valid = self.client.post(
            "/api/v1/context/retrieve",
            json={"query": "CUDA inference", "top_k": 5},
        )
        self.assertEqual(valid.status_code, 200)
        self.assertTrue(valid.json()["results"])
        self.assertTrue(all(result["user_id"] == "demo-user" for result in valid.json()["results"]))

    def test_invalid_request_and_empty_query_return_validation_errors(self) -> None:
        invalid_import = self.client.post(
            "/api/v1/conversations/import",
            json={"conversation_id": "c1", "messages": []},
        )
        empty_query = self.client.post(
            "/api/v1/context/retrieve",
            json={"query": "   "},
        )
        spoofed_user = self.client.post(
            "/api/v1/context/retrieve", json={"user_id": "user-b", "query": "hello"}
        )
        self.assertEqual(invalid_import.status_code, 422)
        self.assertEqual(empty_query.status_code, 422)
        self.assertEqual(spoofed_user.status_code, 422)

    def test_embedding_configuration_error_is_sanitized_http_error(self) -> None:
        def unavailable() -> MemoraService:
            raise EmbeddingConfigurationError("OPENAI_API_KEY is required")

        with TestClient(create_app(
            service_factory=unavailable,
            security_config=self.security,
        )) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            response = client.post(
                "/api/v1/context/retrieve",
                json={"query": "hello"},
                headers={"Authorization": f"Bearer {self.token}"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "OPENAI_API_KEY is required"})

    def test_chatgpt_export_multipart_upload_and_duplicate_summary(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "chatgpt" / "conversations.json"
        first = self.client.post(
            "/api/v1/import/chatgpt",
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
            files=[("files", ("conversations.json", fixture.read_bytes(), "application/json"))],
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["conversations_imported"], 0)

    def test_chatgpt_upload_requires_file(self) -> None:
        missing_file = self.client.post(
            "/api/v1/import/chatgpt"
        )
        self.assertEqual(missing_file.status_code, 422)

    def test_sensitive_endpoints_require_valid_bearer_token(self) -> None:
        headers = self.client.headers.copy()
        self.client.headers.pop("Authorization")
        missing = self.client.post("/api/v1/context/retrieve", json={"query": "hello"})
        invalid = self.client.post(
            "/api/v1/context/retrieve",
            json={"query": "hello"},
            headers={"Authorization": "Bearer wrong-token"},
        )
        malformed = self.client.post(
            "/api/v1/context/retrieve",
            json={"query": "hello"},
            headers={"Authorization": f"Basic {self.token}"},
        )
        self.client.headers.update(headers)
        valid = self.client.post("/api/v1/context/retrieve", json={"query": "hello"})
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(malformed.status_code, 401)
        self.assertEqual(valid.status_code, 200)
        self.assertNotIn("token", missing.json()["detail"].lower())

        conversation_missing = self.client.post(
            "/api/v1/conversations/import",
            json=self._conversation(),
            headers={"Authorization": ""},
        )
        fixture = ROOT / "tests" / "fixtures" / "chatgpt" / "conversations.json"
        history_missing = self.client.post(
            "/api/v1/import/chatgpt",
            files=[("files", ("conversations.json", fixture.read_bytes(), "application/json"))],
            headers={"Authorization": ""},
        )
        self.assertEqual(conversation_missing.status_code, 401)
        self.assertEqual(history_missing.status_code, 401)

    def test_query_and_top_k_limits_apply_before_embedding(self) -> None:
        calls_before = self.service.embeddings.embed_query_calls
        boundary = self.client.post(
            "/api/v1/context/retrieve", json={"query": "x" * 2000, "top_k": 10}
        )
        calls_after_boundary = self.service.embeddings.embed_query_calls
        oversized = self.client.post(
            "/api/v1/context/retrieve", json={"query": "x" * 2001, "top_k": 1}
        )
        too_low = self.client.post(
            "/api/v1/context/retrieve", json={"query": "x", "top_k": 0}
        )
        too_high = self.client.post(
            "/api/v1/context/retrieve", json={"query": "x", "top_k": 11}
        )
        self.assertEqual(boundary.status_code, 200)
        self.assertEqual(calls_after_boundary, calls_before + 1)
        self.assertEqual(oversized.status_code, 422)
        self.assertEqual(too_low.status_code, 422)
        self.assertEqual(too_high.status_code, 422)
        self.assertEqual(self.service.embeddings.embed_query_calls, calls_after_boundary)

    def test_rate_limit_rejects_before_embedding(self) -> None:
        security = LocalSecurityConfig(
            token="rate-test-token-000000000000000000", user_id="user-a", retrieval_limit=1,
        )
        with TestClient(create_app(
            service_factory=lambda: self.service,
            security_config=security,
        )) as client:
            headers = {"Authorization": "Bearer rate-test-token-000000000000000000"}
            first = client.post("/api/v1/context/retrieve", json={"query": "first"}, headers=headers)
            calls = self.service.embeddings.embed_query_calls
            second = client.post("/api/v1/context/retrieve", json={"query": "second"}, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(self.service.embeddings.embed_query_calls, calls)

    def test_import_rate_limit_and_file_count_reject_before_embedding(self) -> None:
        security = LocalSecurityConfig(
            token="import-rate-token-0000000000000000", user_id="demo-user", import_limit=1,
        )
        with TestClient(create_app(
            service_factory=lambda: self.service,
            security_config=security,
        )) as client:
            headers = {"Authorization": "Bearer import-rate-token-0000000000000000"}
            first = client.post(
                "/api/v1/conversations/import", json=self._conversation(), headers=headers
            )
            calls = self.service.embeddings.embed_document_calls
            second = client.post(
                "/api/v1/conversations/import", json=self._conversation(), headers=headers
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(self.service.embeddings.embed_document_calls, calls)

        many_files = [("files", (f"{index}.json", b"[]", "application/json")) for index in range(11)]
        response = self.client.post("/api/v1/import/chatgpt", files=many_files)
        self.assertEqual(response.status_code, 422)

    def test_cross_user_import_and_replacement_fields_are_rejected(self) -> None:
        payload = self._conversation()
        payload["user_id"] = "user-b"
        response = self.client.post("/api/v1/conversations/import", json=payload)
        self.assertEqual(response.status_code, 422)


class CountingLocalEmbeddingService(LocalHashEmbeddingService):
    def __init__(self) -> None:
        super().__init__(dimensions=256)
        self.embed_query_calls = 0
        self.embed_document_calls = 0

    def embed_query(self, text: str):
        self.embed_query_calls += 1
        return super().embed_query(text)

    def embed_documents(self, texts):
        self.embed_document_calls += 1
        return super().embed_documents(texts)


if __name__ == "__main__":
    unittest.main()
