import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.bulk_import import ChatGPTBulkImportService
from backend.ingestion.chatgpt_export import ChatGPTExportImporter
from backend.ingestion.chunker import ConversationChunker
from backend.models import MessageRole
from backend.rag.local_embeddings import LocalHashEmbeddingService
from backend.rag.retriever import SemanticMemoryRetriever


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "chatgpt" / "conversations.json"


class ChatGPTExportImporterTests(unittest.TestCase):
    def test_graph_and_flat_conversations_are_normalized(self) -> None:
        batch = ChatGPTExportImporter().import_uploads(
            (("conversations.json", FIXTURE.read_bytes()),), user_id="user-one"
        )
        self.assertEqual(batch.conversations_found, 4)
        self.assertEqual(len(batch.conversations), 3)
        self.assertEqual(len(batch.errors), 1)

        rocket = batch.conversations[0]
        self.assertEqual(rocket.conversation.id, "export-normal-1")
        self.assertEqual(rocket.conversation.title, "Synthetic Rocket Project")
        self.assertIsNotNone(rocket.conversation.created_at)
        self.assertIsNotNone(rocket.conversation.updated_at)
        self.assertEqual([message.role for message in rocket.messages], [MessageRole.USER, MessageRole.ASSISTANT])
        self.assertEqual([message.ordinal for message in rocket.messages], [0, 1])
        self.assertNotIn("abandoned branch", " ".join(message.content for message in rocket.messages))

        flat = batch.conversations[1]
        self.assertEqual([message.content for message in flat.messages], [
            "I planted fictional purple tomatoes in the north bed.",
            "Water them early in the morning.",
        ])

    def test_unsupported_non_text_content_is_skipped(self) -> None:
        batch = ChatGPTExportImporter().import_uploads(
            (("conversations.json", FIXTURE.read_bytes()),), user_id="user-one"
        )
        mixed = next(item for item in batch.conversations if item.conversation.id == "export-media-3")
        self.assertEqual(len(mixed.messages), 1)
        self.assertEqual(mixed.messages[0].content, "Keep this fake textual memory.")

    def test_zip_is_inspected_without_extracting_assets(self) -> None:
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("export/conversations.json", FIXTURE.read_bytes())
            archive.writestr("export/image.png", b"not relevant")
        batch = ChatGPTExportImporter().import_uploads(
            (("chatgpt-export.zip", archive_bytes.getvalue()),), user_id="user-one"
        )
        self.assertEqual(batch.conversations_found, 4)
        self.assertEqual(len(batch.conversations), 3)

    def test_unsafe_zip_path_is_rejected_without_extraction(self) -> None:
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("../conversations.json", b"[]")
        batch = ChatGPTExportImporter().import_uploads(
            (("chatgpt-export.zip", archive_bytes.getvalue()),), user_id="user-one"
        )
        self.assertEqual(batch.conversations, ())
        self.assertRegex(batch.errors[0].message, "unsafe path")


class BulkImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SQLiteVectorStore(Path(self.temp_dir.name) / "bulk.sqlite3")
        self.embeddings = LocalHashEmbeddingService(dimensions=128)
        self.service = ChatGPTBulkImportService(
            importer=ChatGPTExportImporter(),
            chunker=ConversationChunker(max_tokens=80, overlap_tokens=20),
            embeddings=self.embeddings,
            store=self.store,
        )
        self.uploads = (("conversations.json", FIXTURE.read_bytes()),)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_bulk_statistics_and_duplicate_protection(self) -> None:
        first = self.service.import_uploads(self.uploads, user_id="user-one")
        second = self.service.import_uploads(self.uploads, user_id="user-one")
        self.assertEqual(first.conversations_found, 4)
        self.assertEqual(first.conversations_imported, 3)
        self.assertEqual(first.conversations_skipped, 1)
        self.assertEqual(first.messages_imported, 5)
        self.assertGreater(first.chunks_indexed, 0)
        self.assertEqual(second.conversations_imported, 0)
        self.assertEqual(second.conversations_skipped, 4)
        self.assertEqual(second.chunks_indexed, 0)

    def test_duplicate_detection_and_retrieval_are_user_scoped(self) -> None:
        self.service.import_uploads(self.uploads, user_id="user-one")
        other = self.service.import_uploads(self.uploads, user_id="user-two")
        self.assertEqual(other.conversations_imported, 3)
        results = SemanticMemoryRetriever(self.embeddings, self.store).retrieve(
            "purple tomatoes north bed", user_id="user-two", limit=3
        )
        self.assertTrue(results)
        self.assertTrue(all(result.user_id == "user-two" for result in results))


if __name__ == "__main__":
    unittest.main()
