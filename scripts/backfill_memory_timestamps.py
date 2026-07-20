"""Backfill trusted historical timestamps without re-embedding stored memories."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from backend.database.timestamp_backfill import backfill_memory_timestamps


def main() -> int:
    try:
        database_path = _database_path(_required_environment("MEMORA_DATABASE_URL"))
        user_id = _required_environment("MEMORA_USER_ID")
        summary = backfill_memory_timestamps(database_path, user_id=user_id)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(_safe_error(exc), file=sys.stderr)
        return 1
    values = (
        ("Chunks examined", summary.chunks_examined),
        ("Chunks updated from message timestamps", summary.chunks_updated_from_message_timestamps),
        ("Chunks updated from conversation timestamps", summary.chunks_updated_from_conversation_timestamps),
        ("Chunks unchanged", summary.chunks_unchanged),
        ("Document chunks updated", summary.document_chunks_updated),
        ("Fallback timestamps retained", summary.fallback_timestamps_retained),
    )
    for label, value in values:
        print(f"{label}: {value}")
    print(f"Duration: {summary.duration_seconds:.3f}s")
    return 0


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required.")
    return value


def _database_path(url: str) -> Path:
    prefix = "sqlite:///"
    if not url.startswith(prefix) or not url[len(prefix):]:
        raise ValueError("MEMORA_DATABASE_URL must use sqlite:///path.")
    return Path(url[len(prefix):])


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    if message.startswith(("MEMORA_", "Configured ")):
        return message
    return "Timestamp backfill failed safely."


if __name__ == "__main__":
    raise SystemExit(main())
