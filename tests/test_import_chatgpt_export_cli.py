import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.bulk_import import ChatGPTBulkImportService
from backend.ingestion.chatgpt_attachments import (
    _library_matches, _normalize_identifier_candidates,
)
from backend.ingestion.chatgpt_export import ChatGPTExportImporter
from backend.ingestion.chunker import ConversationChunker
from backend.rag.local_embeddings import LocalHashEmbeddingService
from scripts.import_chatgpt_export import main


def synthetic_pdf(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output)); output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output); output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


class ExtractedExportCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "export"
        self.root.mkdir()
        self.database = Path(self.temp.name) / "memora.sqlite3"
        self.environment = {
            "MEMORA_DATABASE_URL": f"sqlite:///{self.database}",
            "MEMORA_USER_ID": "cli-user",
            "MEMORA_EMBEDDING_PROVIDER": "local",
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_export(self, *, manifest_path: str = "file-practice.dat") -> None:
        conversation = [{
            "id": "course-conversation", "title": "COMP 472 Practice Exam",
            "messages": [{
                "id": "message-1", "role": "user",
                "content": "I uploaded my practice examination.",
                "metadata": {"attachments": [{
                    "id": "file-practice", "name": "private-practice.pdf",
                    "mime_type": "application/pdf", "size": 900,
                }]},
            }],
        }]
        (self.root / "conversations-000.json").write_text(json.dumps(conversation), encoding="utf-8")
        (self.root / "library_files.json").write_text(json.dumps([{
            "id": {"id": "file-practice", "partition_key": "not-an-identifier"},
            "file_id": "exported-file-practice", "file_name": "private-practice.pdf",
            "file_extension": "pdf", "mime_type": "application/pdf",
            "origination_thread_id": "course-conversation",
            "origination_message_id": "message-1",
        }]), encoding="utf-8")
        (self.root / "conversation_asset_file_names.json").write_text(json.dumps({
            "file-practice.dat": "private-practice.pdf",
        }), encoding="utf-8")
        (self.root / "export_manifest.json").write_text(json.dumps({"logical_files": {
            "file-practice.dat": {"files": [manifest_path]},
        }}), encoding="utf-8")
        if ".." not in Path(manifest_path).parts:
            (self.root / "file-practice.dat").write_bytes(synthetic_pdf(
                "Practice Examination Question 2 covers heuristic search and evaluation."
            ))

    def test_directory_import_is_incremental_private_and_idempotent(self) -> None:
        self._write_export()
        store = SQLiteVectorStore(self.database)
        ChatGPTBulkImportService(
            importer=ChatGPTExportImporter(), chunker=ConversationChunker(),
            embeddings=LocalHashEmbeddingService(), store=store,
        ).import_uploads((("existing.json", json.dumps([{
            "id": "existing-conversation", "title": "Preserved",
            "messages": [{"role": "user", "content": "Existing database sentinel."}],
        }]).encode()),), user_id="cli-user")

        first_out = io.StringIO()
        with patch.dict(os.environ, self.environment, clear=False), redirect_stdout(first_out):
            self.assertEqual(main([str(self.root)]), 0)
        first = first_out.getvalue()
        self.assertIn("Attachments found: 1", first)
        self.assertIn("PDF binaries indexed: 1", first)
        self.assertNotIn("private-practice.pdf", first)
        self.assertNotIn("heuristic search", first)
        self.assertNotIn(str(self.root), first)
        with store._connection() as db:
            self.assertEqual(db.execute("SELECT title FROM conversations WHERE id='existing-conversation'").fetchone(), ("Preserved",))
            self.assertEqual(db.execute("SELECT count(*) FROM attachments").fetchone()[0], 1)
            self.assertGreater(db.execute("SELECT count(*) FROM document_chunks").fetchone()[0], 0)

        second_out = io.StringIO()
        with patch.dict(os.environ, self.environment, clear=False), redirect_stdout(second_out):
            self.assertEqual(main([str(self.root)]), 0)
        second = second_out.getvalue()
        self.assertIn("Conversations imported: 0", second)
        self.assertIn("Attachments imported: 0", second)
        self.assertIn("PDF binaries indexed: 0", second)

    def test_manifest_traversal_is_not_followed(self) -> None:
        self._write_export(manifest_path="../outside.dat")
        (Path(self.temp.name) / "outside.dat").write_bytes(synthetic_pdf("Outside secret content."))
        output = io.StringIO()
        with patch.dict(os.environ, self.environment, clear=False), redirect_stdout(output):
            self.assertEqual(main([str(self.root)]), 0)
        self.assertIn("PDF binaries resolved: 0", output.getvalue())
        store = SQLiteVectorStore(self.database)
        with store._connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM documents").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT binary_resolution_status FROM attachments").fetchone(), ("metadata_only",))

    def test_missing_directory_and_configuration_fail_without_echoing_path(self) -> None:
        error = io.StringIO()
        missing = Path(self.temp.name) / "private-missing-export"
        with redirect_stderr(error):
            self.assertEqual(main([str(missing)]), 1)
        self.assertNotIn(str(missing), error.getvalue())
        self._write_export()
        error = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(error):
            self.assertEqual(main([str(self.root)]), 1)
        self.assertIn("MEMORA_DATABASE_URL is required", error.getvalue())

    def test_real_nested_library_id_and_malformed_shapes_normalize_conservatively(self) -> None:
        self.assertEqual(
            _normalize_identifier_candidates({
                "id": "valid-id", "partition_key": "must-not-match",
            }),
            ("valid-id",),
        )
        self.assertEqual(
            _normalize_identifier_candidates([
                None, {"unrelated": "ignored"}, {"id": [{"id": "nested-id"}]},
            ]),
            ("nested-id",),
        )
        self.assertEqual(_normalize_identifier_candidates({"unexpected": {"id": "hidden"}}), ())
        self.assertEqual(_normalize_identifier_candidates(123), ())

        raw = {
            "id": {"id": "valid-id"}, "name": "synthetic.pdf",
            "conversation_id": "conversation-a", "source_message_id": "message-a",
        }
        matching = _library_matches(raw, [{
            "id": {"id": "valid-id", "partition_key": "ignored"},
            "file_id": None, "file_name": "synthetic.pdf",
            "origination_thread_id": {"id": "conversation-a"},
            "origination_message_id": [None, {"id": "message-a"}],
        }])
        self.assertEqual(len(matching), 1)
        self.assertEqual(_library_matches(raw, [{
            "id": {"unrelated": "valid-id"}, "file_id": [None, {"other": "valid-id"}],
            "file_name": "different.pdf", "origination_thread_id": {"other": "conversation-a"},
        }]), [])


if __name__ == "__main__":
    unittest.main()
