"""Update-only trusted timestamp repair for previously indexed SQLite metadata."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from contextlib import closing


@dataclass(frozen=True, slots=True)
class TimestampBackfillSummary:
    chunks_examined: int
    chunks_updated_from_message_timestamps: int
    chunks_updated_from_conversation_timestamps: int
    chunks_unchanged: int
    document_chunks_updated: int
    fallback_timestamps_retained: int
    duration_seconds: float


def backfill_memory_timestamps(database_path: Path | str, *, user_id: str) -> TimestampBackfillSummary:
    """Repair timestamp metadata only; never modify content, vectors, IDs, or fingerprints."""
    if not user_id.strip():
        raise ValueError("MEMORA_USER_ID is required.")
    path = Path(database_path)
    if not path.is_file():
        raise ValueError("Configured Memora database does not exist.")
    started = perf_counter()
    counts = {
        "examined": 0, "messages": 0, "conversations": 0,
        "unchanged": 0, "documents": 0, "fallback": 0,
    }
    with closing(sqlite3.connect(path)) as db, db:
        _validate_schema(db)
        messages = {
            message_id: timestamp
            for message_id, raw in db.execute(
                "SELECT id, created_at FROM messages WHERE user_id = ? AND created_at IS NOT NULL",
                (user_id,),
            )
            if (timestamp := _valid_timestamp(raw)) is not None
        }
        conversations = {
            conversation_id: (_valid_timestamp(updated_at), _valid_timestamp(created_at))
            for conversation_id, updated_at, created_at in db.execute(
                "SELECT id, updated_at, created_at FROM conversations WHERE user_id = ?",
                (user_id,),
            )
        }
        chunks = db.execute(
            """SELECT id, conversation_id, message_ids, created_at
               FROM chunks WHERE user_id = ?""",
            (user_id,),
        ).fetchall()
        counts["examined"] = len(chunks)
        for chunk_id, conversation_id, raw_message_ids, current_raw in chunks:
            message_times = [
                messages[message_id] for message_id in _message_ids(raw_message_ids)
                if message_id in messages
            ]
            source = "messages" if message_times else "conversations"
            desired = max(message_times, default=None)
            if desired is None:
                updated_at, created_at = conversations.get(conversation_id, (None, None))
                desired = updated_at or created_at
            if desired is None:
                counts["fallback"] += 1
                counts["unchanged"] += 1
                continue
            if _same_instant(current_raw, desired):
                counts["unchanged"] += 1
                continue
            db.execute(
                "UPDATE chunks SET created_at = ? WHERE id = ? AND user_id = ?",
                (_iso(desired), chunk_id, user_id),
            )
            counts[source] += 1

        attachment_messages: dict[str, list[datetime]] = {}
        linked_documents: set[str] = set()
        for document_id, message_id in db.execute(
            """SELECT document_id, message_id FROM attachments
               WHERE user_id = ? AND document_id IS NOT NULL""",
            (user_id,),
        ):
            linked_documents.add(document_id)
            timestamp = messages.get(message_id)
            if timestamp is not None:
                attachment_messages.setdefault(document_id, []).append(timestamp)
        document_chunks = db.execute(
            """SELECT dc.id, dc.created_at, d.id, d.parent_conversation_id
               FROM document_chunks dc JOIN documents d ON d.id = dc.document_id
               WHERE dc.user_id = ? AND d.user_id = ?""",
            (user_id, user_id),
        ).fetchall()
        for chunk_id, current_raw, document_id, parent_id in document_chunks:
            linked_times = attachment_messages.get(document_id, ())
            desired = max(linked_times, default=None)
            if desired is None and parent_id and document_id in linked_documents:
                updated_at, created_at = conversations.get(parent_id, (None, None))
                desired = updated_at or created_at
            if desired is None:
                counts["fallback"] += 1
                continue
            if _same_instant(current_raw, desired):
                continue
            db.execute(
                "UPDATE document_chunks SET created_at = ? WHERE id = ? AND user_id = ?",
                (_iso(desired), chunk_id, user_id),
            )
            counts["documents"] += 1

    return TimestampBackfillSummary(
        chunks_examined=counts["examined"],
        chunks_updated_from_message_timestamps=counts["messages"],
        chunks_updated_from_conversation_timestamps=counts["conversations"],
        chunks_unchanged=counts["unchanged"],
        document_chunks_updated=counts["documents"],
        fallback_timestamps_retained=counts["fallback"],
        duration_seconds=perf_counter() - started,
    )


def _validate_schema(db: sqlite3.Connection) -> None:
    required = {
        "conversations": {"id", "user_id", "created_at", "updated_at"},
        "messages": {"id", "user_id", "created_at"},
        "chunks": {"id", "conversation_id", "user_id", "message_ids", "created_at"},
        "documents": {"id", "user_id", "parent_conversation_id"},
        "document_chunks": {"id", "document_id", "user_id", "created_at"},
        "attachments": {"user_id", "message_id", "document_id"},
    }
    for table, columns in required.items():
        available = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if not columns <= available:
            raise ValueError("Configured database does not have the required Memora timestamp schema.")


def _message_ids(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _valid_timestamp(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _same_instant(raw: object, desired: datetime) -> bool:
    current = _valid_timestamp(raw)
    return current is not None and current == desired.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
