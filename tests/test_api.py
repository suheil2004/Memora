import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.security import LocalSecurityConfig
from backend.api.service import MemoraService
from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import JsonConversationImporter
from backend.interfaces import RetrievalResult
from backend.models import (
    Attachment, BinaryResolutionStatus, Document, DocumentChunk,
)
from backend.rag.context_builder import CompactContextBuilder
from backend.rag.local_embeddings import LocalHashEmbeddingService
from backend.rag.openai_embeddings import EmbeddingConfigurationError
from backend.rag.reranker import extract_course_codes


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

    def test_cors_does_not_allow_an_unlisted_web_origin(self) -> None:
        response = self.client.options(
            "/api/v1/context/retrieve",
            headers={
                "Origin": "https://malicious.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

        self.assertNotIn("access-control-allow-origin", response.headers)

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
        self.assertNotIn("briefs", body)
        self.assertNotIn("threads", body)
        self.assertEqual(len(body["memories"]), 1)
        memory = body["memories"][0]
        self.assertEqual(memory["title"], "Drone Detection Project")
        self.assertEqual(memory["subject"], "user")
        self.assertTrue(memory["summary"])
        self.assertTrue(memory["key_details"])
        self.assertEqual(memory["latest_timestamp"], "2026-07-01T12:00:00Z")
        self.assertEqual(memory["sources"], [{
            "type": "conversation",
            "conversation_id": "conv_drone_001",
            "conversation_title": "Drone Detection Project",
        }])
        self.assertNotIn("score", memory)
        self.assertNotIn("source_message_ids", memory)
        self.assertNotIn("source_chunk_ids", memory)
        self.assertIn("Drone Detection Project", body["context"])
        result = body["results"][0]
        self.assertEqual(result["user_id"], "demo-user")
        self.assertEqual(result["conversation_id"], "conv_drone_001")
        self.assertEqual(result["conversation_title"], "Drone Detection Project")
        self.assertTrue(result["chunk_id"])
        self.assertTrue(result["source_message_ids"])
        self.assertIsInstance(result["score"], float)

    def test_retrieval_abstains_for_unrelated_queries(self) -> None:
        imported = self.client.post(
            "/api/v1/conversations/import", json=self._conversation()
        )
        self.assertEqual(imported.status_code, 200, imported.text)

        for query in (
            "How was the camera feed being processed in my drone detection setup?",
            "What computer was doing inference for my drone project?",
        ):
            with self.subTest(query=query):
                response = self.client.post(
                    "/api/v1/context/retrieve",
                    json={"query": query, "top_k": 5, "min_similarity": -1.0},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["results"])
                self.assertEqual(
                    response.json()["results"][0]["conversation_title"],
                    "Drone Detection Project",
                )

        for query in (
            "What is my workout plan?",
            "Where did I leave my keys?",
            "What medicine did I take yesterday?",
        ):
            with self.subTest(query=query):
                response = self.client.post(
                    "/api/v1/context/retrieve",
                    json={"query": query, "top_k": 5, "min_similarity": -1.0},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["results"], [])
                self.assertEqual(response.json()["context"], "")
                self.assertEqual(response.json()["memories"], [])

    def test_service_uses_larger_internal_pool_then_limits_distinct_results(self) -> None:
        candidates = tuple(
            RetrievalResult(
                content=f"assignment detail {index}",
                score=0.9 - index / 100,
                source_kind="chunk",
                source_id=f"chunk-{index}",
                conversation_id="same-conversation" if index < 3 else f"conversation-{index}",
                conversation_title="Assignment Notes" if index < 3 else f"Source {index}",
                user_id="demo-user",
                source_message_ids=(f"message-{index}",),
            )
            for index in range(8)
        )
        recording = RecordingRetriever(candidates)
        self.service.retriever = recording

        response = self.service.retrieve_context(
            "assignment", user_id="demo-user", top_k=3, min_similarity=-1.0
        )

        self.assertEqual(recording.limit, 20)
        self.assertEqual(len(response.results), 3)
        self.assertEqual(len({item.conversation_id for item in response.results}), 3)
        self.assertEqual(response.results[0].source_message_ids, ("message-0",))
        self.assertIn("Assignment Notes", response.context)
        self.assertIsNotNone(response.timing)
        self.assertGreaterEqual(response.timing.total_ms, response.timing.synthesis_ms)

        expanded = self.service.retrieve_context(
            "assignment", user_id="demo-user", top_k=10, min_similarity=-1.0
        )
        self.assertEqual(recording.limit, 20)
        self.assertEqual(len(expanded.threads), 5)
        self.assertEqual(len(expanded.results), 5)
        self.assertEqual(len(expanded.briefs), 5)
        self.assertTrue(all(brief.used_fallback for brief in expanded.briefs))
        self.assertEqual(
            [brief.thread_id for brief in expanded.briefs],
            [thread.thread_id for thread in expanded.threads],
        )

    def test_entity_dominant_course_query_uses_exact_user_scoped_chunks_only(self) -> None:
        conversations = (
            ("comp-assignment", "COMP 472 Assignment", "My COMP472 assignment covered search algorithms."),
            ("comp-exam", "COMP-472 Practice Exam", "My COMP 472 practice exam covered heuristics."),
            ("comp-project", "COMP 472 Course Project", "My COMP-472 project evaluated an AI agent."),
            ("engr-project", "ENGR 290 Project", "My ENGR 290 project used Firebase."),
            ("firebase", "Android Coursework", "My Firebase Android application was coursework."),
        )
        for conversation_id, title, content in conversations:
            self.service.import_conversation({
                "conversation_id": conversation_id,
                "title": title,
                "messages": [{"role": "user", "content": content}],
            }, user_id="demo-user")
        query_calls = self.service.embeddings.embed_query_calls

        response = self.service.retrieve_context(
            "Tell me about COMP 472", user_id="demo-user", top_k=5, min_similarity=1.0
        )

        self.assertEqual(self.service.embeddings.embed_query_calls, query_calls)
        self.assertEqual(len(response.threads), 3)
        self.assertTrue(all(
            "COMP 472" in {
                code for text in (thread.title, *thread.supporting_chunks)
                for code in extract_course_codes(text)
            }
            for thread in response.threads
        ))
        self.assertNotIn(
            "engr-project", {result.conversation_id for result in response.results}
        )

        engr_response = self.service.retrieve_context(
            "Tell me about ENGR 290", user_id="demo-user", top_k=5, min_similarity=1.0
        )
        self.assertEqual(
            {result.conversation_id for result in engr_response.results}, {"engr-project"}
        )

    def test_task_query_ranks_within_conversation_level_course_scope(self) -> None:
        conversations = (
            ("comp-exam", "COMP 472 Artificial Intelligence", "My practice exam covered search algorithms and machine learning."),
            ("comp-assignment", "COMP 472 Artificial Intelligence", "My assignment implemented a game-search agent."),
            ("control-exam", "COEN 311 Control Systems", "My practice exam covered root locus and Routh-Hurwitz."),
            ("firebase", "ENGR 290 Project", "My project built a Firebase Android application."),
        )
        for conversation_id, title, content in conversations:
            self.service.import_conversation({
                "conversation_id": conversation_id,
                "title": title,
                "messages": [{"role": "user", "content": content}],
            }, user_id="demo-user")

        response = self.service.retrieve_context(
            "What practice exams did I discuss for COMP 472?",
            user_id="demo-user", top_k=5, min_similarity=1.0,
        )

        result_ids = [result.conversation_id for result in response.results]
        self.assertEqual(result_ids[0], "comp-exam")
        self.assertEqual(set(result_ids), {"comp-exam", "comp-assignment"})
        self.assertNotIn("COMP 472", response.results[0].content)
        self.assertNotIn("control-exam", result_ids)
        self.assertNotIn("firebase", result_ids)

    def test_multi_course_conversation_requires_unambiguous_chunk_evidence(self) -> None:
        self.service.import_conversation({
            "conversation_id": "shared-courses",
            "title": "Shared Academic Discussion",
            "messages": [
                {"role": "user", "content": "COMP 472 and COEN 352 were both discussed. " + "overview " * 90},
                {"role": "user", "content": "COMP 472 assignment used heuristic search. " + "detail " * 90},
                {"role": "user", "content": "This unlabelled practice exam chunk is ambiguous. " + "practice " * 90},
            ],
        }, user_id="demo-user")

        response = self.service.retrieve_context(
            "What assignments did I work on for COMP 472?",
            user_id="demo-user", top_k=5, min_similarity=1.0,
        )

        self.assertEqual(len(response.results), 1)
        self.assertIn("COMP 472 assignment", response.results[0].content)
        self.assertNotIn("both discussed", response.results[0].content)
        self.assertNotIn("unlabelled practice exam", response.results[0].content)

    def test_retrieval_is_user_isolated(self) -> None:
        imported = self.client.post("/api/v1/conversations/import", json=self._conversation())
        self.assertEqual(imported.status_code, 200)
        query = "drone detection camera feed inference CUDA"
        response = self.client.post(
            "/api/v1/context/retrieve",
            json={"user_id": "user-b", "query": query, "top_k": 5},
        )
        self.assertEqual(response.status_code, 422)

        valid = self.client.post(
            "/api/v1/context/retrieve",
            json={"query": query, "top_k": 5},
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

    def test_chatgpt_upload_rejects_oversized_body(self) -> None:
        with patch.dict(os.environ, {"MEMORA_CHATGPT_MAX_UPLOAD_BYTES": "32"}):
            response = self.client.post(
                "/api/v1/import/chatgpt",
                files=[("files", ("conversations.json", b"x" * 100_000, "application/json"))],
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "uploaded export exceeds the size limit"})
        self.assertLess(len(response.content), 200)

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

    def test_all_sensitive_endpoints_reject_missing_authentication(self) -> None:
        requests = (
            ("GET", "/api/v1/memory/stats", {}),
            ("DELETE", "/api/v1/memory", {}),
            ("POST", "/api/v1/conversations/import", {"json": self._conversation()}),
            ("POST", "/api/v1/context/retrieve", {"json": {"query": "hello"}}),
            ("POST", "/api/v1/import/chatgpt", {
                "files": [("files", ("conversations.json", b"[]", "application/json"))],
            }),
            ("POST", "/api/v1/import/documents", {
                "files": [("files", ("document.pdf", b"%PDF-invalid", "application/pdf"))],
            }),
        )
        for method, path, kwargs in requests:
            with self.subTest(path=path):
                response = self.client.request(
                    method, path, headers={"Authorization": ""}, **kwargs
                )
                self.assertEqual(response.status_code, 401, response.text)

    def test_duplicate_and_very_long_authorization_values_are_rejected(self) -> None:
        duplicate = self.client.get(
            "/api/v1/memory/stats",
            headers=[
                ("Authorization", f"Bearer {self.token}"),
                ("Authorization", f"Bearer {self.token}"),
            ],
        )
        oversized = self.client.get(
            "/api/v1/memory/stats",
            headers={"Authorization": f"Bearer {'x' * 100_000}"},
        )

        self.assertEqual(duplicate.status_code, 401)
        self.assertEqual(oversized.status_code, 401)
        self.assertLess(len(oversized.content), 200)

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

    def test_validation_errors_are_sanitized_bounded_and_keep_field_details(self) -> None:
        oversized_query = "SENSITIVE-QUERY-MARKER-" + ("x" * 100_000)
        calls_before = self.service.embeddings.embed_query_calls

        oversized = self.client.post(
            "/api/v1/context/retrieve", json={"query": oversized_query, "top_k": 5}
        )

        self.assertEqual(oversized.status_code, 422)
        self.assertNotIn(oversized_query, oversized.text)
        self.assertNotIn("SENSITIVE-QUERY-MARKER", oversized.text)
        self.assertLess(len(oversized.content), 10_000)
        self.assertEqual(self.service.embeddings.embed_query_calls, calls_before)
        query_error = oversized.json()["detail"][0]
        self.assertEqual(query_error["loc"], ["body", "query"])
        self.assertEqual(query_error["type"], "string_too_long")
        self.assertIn("at most 2000", query_error["msg"])
        self.assertNotIn("input", query_error)

        ordinary = self.client.post(
            "/api/v1/context/retrieve", json={"query": "valid query", "top_k": 0}
        )
        self.assertEqual(ordinary.status_code, 422)
        top_k_error = ordinary.json()["detail"][0]
        self.assertEqual(top_k_error["loc"], ["body", "top_k"])
        self.assertEqual(top_k_error["type"], "greater_than_equal")
        self.assertTrue(top_k_error["msg"])
        self.assertEqual(self.service.embeddings.embed_query_calls, calls_before)

        valid = self.client.post(
            "/api/v1/context/retrieve", json={"query": "valid query", "top_k": 5}
        )
        self.assertEqual(valid.status_code, 200, valid.text)
        self.assertEqual(self.service.embeddings.embed_query_calls, calls_before + 1)

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

    def test_authenticated_memory_stats_clear_isolation_and_reimport_flow(self) -> None:
        payload = self._conversation()
        self.assertEqual(
            self.client.post("/api/v1/conversations/import", json=payload).status_code, 200
        )
        other_payload = {**payload, "conversation_id": "other-conversation"}
        self.service.import_conversation(other_payload, user_id="other-user")
        with self.service.store._connection() as db:
            message_id = db.execute(
                "SELECT id FROM messages WHERE conversation_id = ? AND user_id = ? LIMIT 1",
                (payload["conversation_id"], "demo-user"),
            ).fetchone()[0]
        document = Document(
            id="privacy-document", user_id="demo-user", filename="synthetic.pdf",
            content_sha256="privacy-hash", parent_conversation_id=payload["conversation_id"],
            page_count=1,
        )
        document_chunk = DocumentChunk(
            id="privacy-document-chunk", document_id=document.id, user_id="demo-user",
            filename=document.filename, parent_conversation_id=payload["conversation_id"],
            page_start=1, page_end=1, content="Synthetic searchable document content.", ordinal=0,
        )
        vector = self.service.embeddings.embed_documents((document_chunk.content,))
        self.service.store.save_document(
            document, (document_chunk,), vector,
            embedding_provider=self.service.embeddings.provider_name,
            embedding_model=self.service.embeddings.model_name,
        )
        self.service.store.upsert_attachments((Attachment(
            id="privacy-attachment", user_id="demo-user",
            conversation_id=payload["conversation_id"], message_id=message_id,
            original_filename="synthetic.pdf", mime_type="application/pdf", size_bytes=1,
            library_file_id=None, document_id=document.id,
            binary_resolution_status=BinaryResolutionStatus.RESOLVED,
        ),))

        unauthenticated = self.client.get(
            "/api/v1/memory/stats", headers={"Authorization": ""}
        )
        wrong = self.client.get(
            "/api/v1/memory/stats", headers={"Authorization": "Bearer wrong-token-value-000000"}
        )
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(
            self.client.delete("/api/v1/memory", headers={"Authorization": ""}).status_code,
            401,
        )
        self.assertEqual(
            self.client.delete(
                "/api/v1/memory",
                headers={"Authorization": "Bearer wrong-token-value-000000"},
            ).status_code,
            401,
        )
        stats = self.client.get("/api/v1/memory/stats")
        self.assertEqual(stats.status_code, 200, stats.text)
        self.assertEqual(stats.json()["conversations"], 1)
        self.assertGreater(stats.json()["conversation_chunks"], 0)
        self.assertEqual(stats.json()["attachments"], 1)
        self.assertEqual(stats.json()["documents"], 1)
        self.assertEqual(stats.json()["document_chunks"], 1)

        self.assertEqual(
            self.client.delete("/api/v1/memory?user_id=other-user").status_code, 422
        )
        self.assertEqual(
            self.client.request("DELETE", "/api/v1/memory", json={"user_id": "other-user"}).status_code,
            422,
        )
        cleared = self.client.delete("/api/v1/memory")
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertTrue(cleared.json()["cleared"])
        self.assertGreater(cleared.json()["rows_deleted"], 0)
        with self.service.store._connection() as db:
            for table in ("conversations", "messages", "chunks", "attachments", "documents", "document_chunks"):
                self.assertEqual(
                    db.execute(f"SELECT count(*) FROM {table} WHERE user_id = 'demo-user'").fetchone()[0],
                    0,
                )
            self.assertGreater(
                db.execute("SELECT count(*) FROM conversations WHERE user_id = 'other-user'").fetchone()[0],
                0,
            )
            self.assertGreater(
                db.execute("SELECT count(*) FROM chunks WHERE user_id = 'other-user'").fetchone()[0],
                0,
            )

        empty = self.client.post(
            "/api/v1/context/retrieve", json={"query": "drone detection CUDA", "top_k": 5}
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["results"], [])
        self.assertEqual(empty.json()["memories"], [])
        self.assertEqual(empty.json()["context"], "")
        repeated = self.client.delete("/api/v1/memory")
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["rows_deleted"], 0)

        reimported = self.client.post("/api/v1/conversations/import", json=payload)
        self.assertEqual(reimported.status_code, 200, reimported.text)
        retrieved = self.client.post(
            "/api/v1/context/retrieve",
            json={"query": "Where does drone detection inference run?", "top_k": 5},
        )
        self.assertEqual(retrieved.status_code, 200)
        self.assertTrue(retrieved.json()["results"])


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


class RecordingRetriever:
    def __init__(self, candidates: tuple[RetrievalResult, ...]) -> None:
        self.candidates = candidates
        self.limit: int | None = None

    def retrieve(self, query, *, user_id, limit, min_similarity):
        self.limit = limit
        return self.candidates[:limit]


if __name__ == "__main__":
    unittest.main()
