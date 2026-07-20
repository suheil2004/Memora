import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.database.sqlite_store import SQLiteVectorStore
from backend.database.timestamp_backfill import backfill_memory_timestamps
from backend.models import MemoryThread
from backend.rag.memory_facts import DeterministicMemoryFactExtractor, temporal_thread_utility
from scripts.backfill_memory_timestamps import main


class TimestampBackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "synthetic.sqlite3"
        SQLiteVectorStore(self.database)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executemany(
                "INSERT INTO users (id,display_name,created_at) VALUES (?,?,?)",
                [("user", None, "2026-07-15T00:00:00+00:00"),
                 ("other", None, "2026-07-15T00:00:00+00:00")],
            )
            db.executemany(
                """INSERT INTO conversations
                   (id,user_id,title,source,created_at,imported_at,external_id,updated_at,import_fingerprint)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [
                    ("old", "user", "Old", "test", "2025-01-01T00:00:00+00:00", "2026-07-15T00:00:00+00:00", "old", "2025-02-01T00:00:00+00:00", "fingerprint-old"),
                    ("current", "user", "Current", "test", "2026-01-01T00:00:00+00:00", "2026-07-15T00:00:00+00:00", "current", "2026-06-01T00:00:00+00:00", "fingerprint-current"),
                    ("fallback", "user", "Fallback", "test", None, "2026-07-15T00:00:00+00:00", "fallback", None, "fingerprint-fallback"),
                    ("other", "other", "Other", "test", "2020-01-01T00:00:00+00:00", "2026-07-15T00:00:00+00:00", "other", None, "fingerprint-other"),
                ],
            )
            db.executemany(
                "INSERT INTO messages (id,conversation_id,user_id,role,content,ordinal,created_at) VALUES (?,?,?,?,?,?,?)",
                [
                    ("m-old", "old", "user", "user", "Synthetic old architecture.", 0, "2025-01-20T00:00:00+00:00"),
                    ("m-current", "current", "user", "user", "Synthetic current architecture.", 0, "2026-06-15T00:00:00+00:00"),
                ],
            )
            db.executemany(
                """INSERT INTO chunks
                   (id,conversation_id,user_id,content,ordinal,message_ids,embedding,
                    embedding_provider,embedding_model,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [
                    ("chunk-old", "old", "user", "User: The original detailed architecture ran inference on the Raspberry Pi.", 0, json.dumps(["m-old"]), "[0.1,0.2]", "local", "model", "2026-07-15T00:00:00+00:00"),
                    ("chunk-current", "current", "user", "User: We switched to the current design using a CUDA Windows laptop.", 0, json.dumps(["m-current"]), "[0.3,0.4]", "local", "model", "2026-07-15T00:00:00+00:00"),
                    ("chunk-conversation", "current", "user", "User: Conversation timestamp fallback.", 1, json.dumps(["missing"]), "[0.5,0.6]", "local", "model", "2026-07-15T00:00:00+00:00"),
                    ("chunk-fallback", "fallback", "user", "User: Import timestamp fallback.", 0, json.dumps(["missing"]), "[0.7,0.8]", "local", "model", "2026-07-15T00:00:00+00:00"),
                    ("chunk-other", "other", "other", "Other user synthetic data.", 0, json.dumps([]), "[0.9,0.0]", "local", "model", "2026-07-15T00:00:00+00:00"),
                ],
            )
            db.executemany(
                """INSERT INTO documents
                   (id,user_id,filename,content_sha256,parent_conversation_id,page_count,extraction_status,imported_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [
                    ("linked-doc", "user", "linked.pdf", "hash-linked", "current", 1, "extracted", "2026-07-15T00:00:00+00:00"),
                    ("standalone-doc", "user", "standalone.pdf", "hash-standalone", "current", 1, "extracted", "2026-07-15T00:00:00+00:00"),
                ],
            )
            db.executemany(
                """INSERT INTO document_chunks
                   (id,document_id,user_id,content,ordinal,page_start,page_end,embedding,
                    embedding_provider,embedding_model,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    ("dc-linked", "linked-doc", "user", "Linked synthetic PDF.", 0, 1, 1, "[0.11,0.0]", "local", "model", "2026-07-15T00:00:00+00:00"),
                    ("dc-standalone", "standalone-doc", "user", "Standalone synthetic PDF.", 0, 1, 1, "[0.12,0.0]", "local", "model", "2026-07-15T00:00:00+00:00"),
                ],
            )
            db.execute(
                """INSERT INTO attachments
                   (id,user_id,conversation_id,message_id,original_filename,mime_type,size_bytes,
                    library_file_id,document_id,binary_resolution_status,imported_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                ("attachment", "user", "current", "m-current", "linked.pdf", "application/pdf", 1,
                 None, "linked-doc", "resolved", "2026-07-15T00:00:00+00:00"),
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _immutable_snapshot(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            return {
                "chunks": db.execute(
                    "SELECT id,content,message_ids,embedding,embedding_provider,embedding_model FROM chunks ORDER BY id"
                ).fetchall(),
                "documents": db.execute(
                    "SELECT id,content,embedding,embedding_provider,embedding_model FROM document_chunks ORDER BY id"
                ).fetchall(),
                "fingerprints": db.execute(
                    "SELECT id,import_fingerprint FROM conversations ORDER BY id"
                ).fetchall(),
            }

    def test_backfill_changes_only_timestamp_metadata_and_is_user_scoped(self) -> None:
        before = self._immutable_snapshot()

        summary = backfill_memory_timestamps(self.database, user_id="user")

        self.assertEqual(summary.chunks_examined, 4)
        self.assertEqual(summary.chunks_updated_from_message_timestamps, 2)
        self.assertEqual(summary.chunks_updated_from_conversation_timestamps, 1)
        self.assertEqual(summary.chunks_unchanged, 1)
        self.assertEqual(summary.document_chunks_updated, 1)
        self.assertEqual(summary.fallback_timestamps_retained, 2)
        self.assertEqual(before, self._immutable_snapshot())
        with closing(sqlite3.connect(self.database)) as db, db:
            timestamps = dict(db.execute("SELECT id,created_at FROM chunks"))
            document_timestamps = dict(db.execute("SELECT id,created_at FROM document_chunks"))
        self.assertEqual(timestamps["chunk-old"], "2025-01-20T00:00:00+00:00")
        self.assertEqual(timestamps["chunk-current"], "2026-06-15T00:00:00+00:00")
        self.assertEqual(timestamps["chunk-conversation"], "2026-06-01T00:00:00+00:00")
        self.assertEqual(timestamps["chunk-fallback"], "2026-07-15T00:00:00+00:00")
        self.assertEqual(timestamps["chunk-other"], "2026-07-15T00:00:00+00:00")
        self.assertEqual(document_timestamps["dc-linked"], "2026-06-15T00:00:00+00:00")
        self.assertEqual(document_timestamps["dc-standalone"], "2026-07-15T00:00:00+00:00")
        retrieved = SQLiteVectorStore(self.database, read_only=True).search(
            (0.1, 0.2), user_id="user", limit=10, min_similarity=-1.0,
            embedding_provider="local", embedding_model="model",
        )
        retrieved_times = {item.source_id: item.source_created_at for item in retrieved}
        self.assertEqual(
            retrieved_times["chunk-old"],
            datetime(2025, 1, 20, tzinfo=timezone.utc),
        )
        self.assertEqual(
            retrieved_times["dc-linked"],
            datetime(2026, 6, 15, tzinfo=timezone.utc),
        )

        repeated = backfill_memory_timestamps(self.database, user_id="user")
        self.assertEqual(repeated.chunks_updated_from_message_timestamps, 0)
        self.assertEqual(repeated.chunks_updated_from_conversation_timestamps, 0)
        self.assertEqual(repeated.document_chunks_updated, 0)
        self.assertEqual(repeated.chunks_unchanged, 4)

    def test_restored_timestamps_support_current_and_historical_ranking(self) -> None:
        with closing(sqlite3.connect(self.database)) as db, db:
            before = dict(db.execute(
                "SELECT id,created_at FROM chunks WHERE id IN ('chunk-old','chunk-current')"
            ))
        self.assertEqual(before["chunk-old"], before["chunk-current"])
        backfill_memory_timestamps(self.database, user_id="user")
        with closing(sqlite3.connect(self.database)) as db, db:
            restored = dict(db.execute(
                "SELECT id,created_at FROM chunks WHERE id IN ('chunk-old','chunk-current')"
            ))
        old_time = datetime.fromisoformat(restored["chunk-old"])
        current_time = datetime.fromisoformat(restored["chunk-current"])
        old = _thread(
            "old", "Original Drone Architecture",
            "User: The original detailed architecture ran inference on the Raspberry Pi.",
            old_time, 0.84,
        )
        current = _thread(
            "current", "Current Drone Architecture",
            "User: We switched to the current design using a CUDA Windows laptop.",
            current_time, 0.76,
        )
        extractor = DeterministicMemoryFactExtractor()
        broad = "Tell me about my drone detection project"
        historical = "What was my original drone architecture?"
        self.assertGreater(
            temporal_thread_utility(broad, current, extractor.extract(current), reference_time=current_time),
            temporal_thread_utility(broad, old, extractor.extract(old), reference_time=current_time),
        )
        self.assertGreater(
            temporal_thread_utility(historical, old, extractor.extract(old), reference_time=current_time),
            temporal_thread_utility(historical, current, extractor.extract(current), reference_time=current_time),
        )

    def test_cli_uses_only_database_and_user_environment_and_prints_safe_counts(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        environment = {
            "MEMORA_DATABASE_URL": f"sqlite:///{self.database}",
            "MEMORA_USER_ID": "user",
        }
        with patch.dict(os.environ, environment, clear=True), redirect_stdout(stdout), redirect_stderr(stderr):
            result = main()
        self.assertEqual(result, 0)
        self.assertEqual(stderr.getvalue(), "")
        output = stdout.getvalue()
        self.assertIn("Chunks examined: 4", output)
        self.assertIn("Document chunks updated: 1", output)
        self.assertNotIn(str(self.database), output)
        self.assertNotIn("Synthetic old architecture", output)
        self.assertNotIn("OPENAI", output)


def _thread(
    suffix: str, title: str, evidence: str, timestamp: datetime, hybrid_score: float,
) -> MemoryThread:
    return MemoryThread(
        thread_id=f"thread-{suffix}", title=title, subject="user", topic="drone",
        goal_or_context="architecture", source_titles=(title,),
        source_conversation_ids=(suffix,), source_chunk_ids=(f"chunk-{suffix}",),
        source_message_ids=(f"m-{suffix}",), strongest_cosine_score=0.7,
        strongest_hybrid_score=hybrid_score, supporting_chunks=(evidence,),
        source_timestamps=(timestamp,),
    )


if __name__ == "__main__":
    unittest.main()
