import unittest
from datetime import datetime, timezone

from backend.models import (
    ConversationChunk,
    MemoryCategory,
    Message,
    MessageRole,
    StructuredMemory,
)


class CoreModelTests(unittest.TestCase):
    def test_message_rejects_blank_content(self) -> None:
        with self.assertRaisesRegex(ValueError, "blank"):
            Message("m1", "c1", "u1", MessageRole.USER, "  ", 0)

    def test_chunk_requires_message_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            ConversationChunk("ch1", "c1", "u1", "context", 0, ())

    def test_structured_memory_validates_confidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            StructuredMemory(
                "sm1", "u1", "Uses Python", MemoryCategory.PREFERENCE, ("c1",), confidence=1.1
            )

    def test_generated_timestamps_are_utc_aware(self) -> None:
        chunk = ConversationChunk("ch1", "c1", "u1", "context", 0, ("m1",))
        self.assertIsInstance(chunk.created_at, datetime)
        self.assertEqual(chunk.created_at.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()

