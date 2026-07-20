import io
import tempfile
import unittest
import json
import zipfile
import sqlite3
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from backend.api.app import create_app
from backend.api.security import LocalSecurityConfig
from backend.api.service import MemoraService
from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.bulk_import import ChatGPTBulkImportService
from backend.ingestion.chatgpt_export import ChatGPTExportImporter
from backend.ingestion.json_importer import JsonConversationImporter
from backend.ingestion.pdf_documents import (
    DocumentImportError, DocumentLimits, PDFDocumentImportService, safe_pdf_filename,
    discover_export_pdfs,
)
from backend.rag.context_builder import CompactContextBuilder
from backend.rag.local_embeddings import LocalHashEmbeddingService


def text_pdf(pages: list[str]) -> bytes:
    objects: list[bytes] = []
    page_ids = [3 + index * 2 for index in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(
        f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] /Count {len(pages)} >>".encode()
    )
    for index, text in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 40 750 Td ({escaped}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents {content_id} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(output)


class PDFDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteVectorStore(Path(self.temp.name) / "documents.sqlite3")
        self.embeddings = LocalHashEmbeddingService(dimensions=128)
        self.importer = PDFDocumentImportService(self.embeddings, self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_text_pdf_pages_import_and_duplicate_skips(self) -> None:
        data = text_pdf([
            "COMP 472 Artificial Intelligence Practice Examination Question 1 search algorithms.",
            "Question 2 asks about heuristic search and machine learning evaluation.",
        ])
        first = self.importer.import_uploads((("practice_exam.pdf", data, None),), user_id="user-a")
        second = self.importer.import_uploads((("renamed.pdf", data, None),), user_id="user-a")
        self.assertEqual((first.documents_imported, first.document_chunks_indexed), (1, 2))
        self.assertEqual((second.documents_skipped, second.document_chunks_indexed), (1, 0))
        results = self.store.search(
            self.embeddings.embed_query("Question 2 heuristic search"), user_id="user-a",
            limit=5, min_similarity=-1, embedding_provider=self.embeddings.provider_name,
            embedding_model=self.embeddings.model_name,
        )
        document = next(result for result in results if "Question 2" in result.content)
        self.assertEqual((document.page_start, document.page_end), (2, 2))
        self.assertEqual(document.document_filename, "practice_exam.pdf")

    def test_malformed_encrypted_no_text_and_limits_fail_safely(self) -> None:
        malformed = self.importer.import_uploads((("bad.pdf", b"%PDF-broken", None),), user_id="u")
        self.assertEqual(malformed.documents_skipped, 1)
        self.assertNotIn("%PDF-broken", " ".join(malformed.errors))

        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        blank = io.BytesIO(); writer.write(blank)
        no_text = self.importer.import_uploads((("scan.pdf", blank.getvalue(), None),), user_id="u")
        self.assertIn("OCR is not supported", no_text.errors[0])

        encrypted_writer = PdfWriter()
        encrypted_writer.add_blank_page(width=100, height=100)
        encrypted_writer.encrypt("secret")
        encrypted = io.BytesIO(); encrypted_writer.write(encrypted)
        protected = self.importer.import_uploads((("locked.pdf", encrypted.getvalue(), None),), user_id="u")
        self.assertIn("password-protected", protected.errors[0])

        tiny = PDFDocumentImportService(self.embeddings, self.store, DocumentLimits(max_file_bytes=20))
        oversized = tiny.import_uploads((("large.pdf", text_pdf(["Enough extractable synthetic text for limits."]), None),), user_id="u")
        self.assertIn("size limit", oversized.errors[0])
        with self.assertRaises(DocumentImportError):
            tiny.import_uploads(tuple((f"{i}.pdf", b"", None) for i in range(6)), user_id="u")

    def test_hostile_filename_is_reduced_to_safe_basename(self) -> None:
        self.assertEqual(safe_pdf_filename("../../private/practice.pdf"), "practice.pdf")
        self.assertEqual(safe_pdf_filename("..\\..\\practice.pdf"), "practice.pdf")

    def test_export_asset_mapping_links_nested_pdf_and_counts_missing_assets(self) -> None:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("conversation_asset_file_names.json", json.dumps({
                "conversation-a": ["practice.pdf", "missing.pdf"],
            }))
            bundle.writestr("nested/assets/practice.pdf", text_pdf(["Synthetic linked PDF text with enough content."]))
        discovery = discover_export_pdfs(
            (("export.zip", archive.getvalue()),), {"conversation-a"}
        )
        self.assertEqual(discovery.references_found, 2)
        self.assertEqual(discovery.binaries_found, 1)
        self.assertEqual(len(discovery.linked_uploads), 1)
        self.assertEqual(discovery.linked_uploads[0][2], "conversation-a")
        self.assertEqual(discovery.missing_assets, 1)

    def test_chatgpt_zip_import_automatically_indexes_reliably_linked_pdf(self) -> None:
        archive = io.BytesIO()
        conversation = [{
            "id": "conversation-a", "title": "COMP 472 Practice Exam",
            "messages": [{
                "id": "m1", "role": "user", "content": "I uploaded the practice exam.",
                "metadata": {"attachments": [{
                    "id": "file-practice", "mime_type": "application/pdf",
                    "name": "practice.pdf", "size": 1000,
                }]},
            }],
        }]
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("conversations.json", json.dumps(conversation))
            bundle.writestr("conversation_asset_file_names.json", json.dumps({
                "file-practice.dat": "practice.pdf",
            }))
            bundle.writestr("library_files.json", json.dumps([{
                "file_id": "file-practice", "file_name": "practice.pdf",
                "file_extension": "pdf", "mime_type": "application/pdf",
                "origination_thread_id": "conversation-a", "origination_message_id": "m1",
            }]))
            bundle.writestr("export_manifest.json", json.dumps({"logical_files": {
                "file-practice.dat": {"files": ["file-practice.dat"], "sharded": False},
            }}))
            bundle.writestr("file-practice.dat", text_pdf([
                "Practice Examination Question 2 covers heuristic search and machine learning.",
            ]))
        summary = ChatGPTBulkImportService(
            importer=ChatGPTExportImporter(), chunker=ConversationChunker(),
            embeddings=self.embeddings, store=self.store,
        ).import_uploads((("export.zip", archive.getvalue()),), user_id="user-a")
        self.assertEqual(summary.documents_found, 1)
        self.assertEqual(summary.documents_imported, 1)
        self.assertEqual(summary.document_chunks_indexed, 1)
        self.assertEqual(summary.attachments_found, 1)
        self.assertEqual(summary.pdf_binaries_resolved, 1)
        response = MemoraService(
            importer=JsonConversationImporter(), chunker=ConversationChunker(),
            embeddings=self.embeddings, store=self.store,
            context_builder=CompactContextBuilder(),
        ).retrieve_context(
            "What was Question 2 on the COMP 472 practice exam?",
            user_id="user-a", top_k=5, min_similarity=-1,
        )
        self.assertEqual(response.results[0].document_filename, "practice.pdf")
        repeated = ChatGPTBulkImportService(
            importer=ChatGPTExportImporter(), chunker=ConversationChunker(),
            embeddings=self.embeddings, store=self.store,
        ).import_uploads((("export.zip", archive.getvalue()),), user_id="user-a")
        self.assertEqual(repeated.conversations_imported, 0)
        self.assertEqual(repeated.attachments_imported, 0)
        self.assertEqual(repeated.documents_imported, 0)
        with self.store._connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM attachments").fetchone()[0], 1)

    def test_metadata_only_and_ambiguous_attachments_are_stored_without_document_chunks(self) -> None:
        archive = io.BytesIO()
        conversations = [{
            "id": "conversation-a", "title": "COMP 472 Practice Exam",
            "messages": [{
                "id": "m1", "role": "user", "content": "I discussed my practice exam.",
                "metadata": {"attachments": [
                    {"id": "missing", "name": "missing.pdf", "mime_type": "application/pdf"},
                    {"id": "ambiguous", "name": "duplicate.pdf", "mime_type": "application/pdf"},
                ]},
            }],
        }]
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("conversations.json", json.dumps(conversations))
            bundle.writestr("conversation_asset_file_names.json", json.dumps({
                "asset-one.dat": "duplicate.pdf", "asset-two.dat": "duplicate.pdf",
            }))
            bundle.writestr("library_files.json", "[]")
            bundle.writestr("export_manifest.json", json.dumps({"logical_files": {
                "asset-one.dat": {"files": ["asset-one.dat"]},
                "asset-two.dat": {"files": ["asset-two.dat"]},
            }}))
            bundle.writestr("asset-one.dat", text_pdf(["First plausible private document candidate."]))
            bundle.writestr("asset-two.dat", text_pdf(["Second plausible private document candidate."]))
        summary = ChatGPTBulkImportService(
            importer=ChatGPTExportImporter(), chunker=ConversationChunker(),
            embeddings=self.embeddings, store=self.store,
        ).import_uploads((("export.zip", archive.getvalue()),), user_id="user-a")

        self.assertEqual(summary.attachments_found, 2)
        self.assertEqual(summary.attachments_metadata_only, 1)
        self.assertEqual(summary.attachments_ambiguous, 1)
        self.assertEqual(summary.pdf_binaries_indexed, 0)
        with self.store._connection() as db:
            statuses = {row[0] for row in db.execute(
                "SELECT binary_resolution_status FROM attachments WHERE user_id='user-a'"
            )}
            document_count = db.execute("SELECT count(*) FROM documents").fetchone()[0]
        self.assertEqual(statuses, {"metadata_only", "ambiguous"})
        self.assertEqual(document_count, 0)
        response = MemoraService(
            importer=JsonConversationImporter(), chunker=ConversationChunker(),
            embeddings=self.embeddings, store=self.store,
            context_builder=CompactContextBuilder(),
        ).retrieve_context(
            "What practice exam did I discuss for COMP 472?",
            user_id="user-a", top_k=5, min_similarity=-1,
        )
        sources = [source for brief in response.briefs for source in brief.attachment_sources]
        self.assertEqual({source.filename for source in sources}, {"missing.pdf", "duplicate.pdf"})

    def test_additive_migration_preserves_conversation_tables(self) -> None:
        path = Path(self.temp.name) / "legacy.sqlite3"
        db = sqlite3.connect(path)
        try:
            db.executescript("""
                CREATE TABLE users (id TEXT PRIMARY KEY, display_name TEXT, created_at TEXT NOT NULL);
                CREATE TABLE conversations (id TEXT, user_id TEXT, title TEXT, source TEXT,
                    created_at TEXT, imported_at TEXT, external_id TEXT, updated_at TEXT,
                    import_fingerprint TEXT, PRIMARY KEY(id,user_id));
                CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT, user_id TEXT,
                    role TEXT, content TEXT, ordinal INTEGER, created_at TEXT);
                CREATE TABLE chunks (id TEXT PRIMARY KEY, conversation_id TEXT, user_id TEXT,
                    content TEXT, ordinal INTEGER, message_ids TEXT, embedding TEXT,
                    embedding_provider TEXT, embedding_model TEXT, created_at TEXT);
                INSERT INTO users VALUES ('u',NULL,'2026-01-01T00:00:00+00:00');
                INSERT INTO conversations VALUES ('c','u','Preserved','test',NULL,
                    '2026-01-01T00:00:00+00:00',NULL,NULL,NULL);
            """)
            db.commit()
        finally:
            db.close()
        upgraded = SQLiteVectorStore(path)
        with upgraded._connection() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            preserved = db.execute("SELECT title FROM conversations WHERE id='c' AND user_id='u'").fetchone()
        self.assertTrue({"conversations", "messages", "chunks", "documents", "document_chunks", "attachments"} <= tables)
        self.assertEqual(preserved, ("Preserved",))

    def test_linked_document_inherits_course_scope_and_excludes_other_course_pdf(self) -> None:
        service = MemoraService(
            importer=JsonConversationImporter(),
            chunker=ConversationChunker(max_tokens=80, overlap_tokens=20),
            embeddings=self.embeddings, store=self.store,
            context_builder=CompactContextBuilder(),
        )
        service.import_conversation({
            "conversation_id": "comp-course", "title": "COMP 472 Artificial Intelligence",
            "messages": [{"role": "user", "content": "I uploaded my practice examination."}],
        }, user_id="user-a")
        service.import_documents(((
            "practice.pdf",
            text_pdf(["Practice Examination Question 2 asks about heuristic search and machine learning."]),
            "comp-course",
        ),), user_id="user-a")
        service.import_documents(((
            "control.pdf",
            text_pdf(["COEN 311 Control Systems Practice Examination Question 2 root locus Routh-Hurwitz."]),
            None,
        ),), user_id="user-a")

        response = service.retrieve_context(
            "What was Question 2 on the COMP 472 practice exam?",
            user_id="user-a", top_k=5, min_similarity=-1,
        )
        document_results = [item for item in response.results if item.document_id]
        self.assertTrue(document_results)
        self.assertEqual(response.results[0].document_filename, "practice.pdf")
        self.assertEqual(document_results[0].document_filename, "practice.pdf")
        self.assertNotIn("control.pdf", {item.document_filename for item in response.results})
        document_sources = [source for brief in response.briefs for source in brief.document_sources]
        self.assertTrue(document_sources)
        self.assertEqual(document_sources[0].page_start, 1)

    def test_authenticated_document_endpoint_sanitizes_filename_and_response(self) -> None:
        service = MemoraService(
            importer=JsonConversationImporter(),
            chunker=ConversationChunker(), embeddings=self.embeddings, store=self.store,
            context_builder=CompactContextBuilder(),
        )
        token = "synthetic-document-token-000000000"
        app = create_app(
            service_factory=lambda: service,
            security_config=LocalSecurityConfig(token=token, user_id="user-a"),
        )
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            unauthenticated = client.post(
                "/api/v1/import/documents",
                files={"files": ("../../private.pdf", text_pdf(["Synthetic document content with enough extractable text."]), "application/pdf")},
            )
            response = client.post(
                "/api/v1/import/documents",
                headers={"Authorization": f"Bearer {token}"},
                files={"files": ("../../private.pdf", text_pdf(["Synthetic document content with enough extractable text."]), "application/pdf")},
            )
            retrieval = client.post(
                "/api/v1/context/retrieve",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": "Synthetic document content", "top_k": 5},
            )
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("..", response.text)
        self.assertNotIn(str(Path(self.temp.name)), response.text)
        self.assertEqual(retrieval.status_code, 200, retrieval.text)
        source = retrieval.json()["memories"][0]["sources"][0]
        self.assertEqual(source["type"], "document")
        self.assertEqual(source["filename"], "private.pdf")
        self.assertNotIn("path", source)


if __name__ == "__main__":
    unittest.main()
