"""SQLite persistence and cosine retrieval for the first vertical slice."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path

from backend.interfaces import Embedding, ImportedConversation, RetrievalResult
from backend.models import ConversationChunk, User


class SQLiteVectorStore:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, display_name TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT NOT NULL, user_id TEXT NOT NULL, title TEXT, source TEXT NOT NULL,
                    created_at TEXT, imported_at TEXT NOT NULL, external_id TEXT,
                    PRIMARY KEY (id, user_id), FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, user_id TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    created_at TEXT, FOREIGN KEY (conversation_id, user_id)
                    REFERENCES conversations(id, user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, user_id TEXT NOT NULL,
                    content TEXT NOT NULL, ordinal INTEGER NOT NULL, message_ids TEXT NOT NULL,
                    embedding TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id, user_id)
                    REFERENCES conversations(id, user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_user ON chunks(user_id);
                """
            )

    def save_import(self, user: User, imported: ImportedConversation) -> None:
        conversation = imported.conversation
        if conversation.user_id != user.id or any(m.user_id != user.id for m in imported.messages):
            raise ValueError("all imported data must belong to the supplied user")
        with self._connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO users (id, display_name, created_at) VALUES (?, ?, ?)",
                (user.id, user.display_name, user.created_at.isoformat()),
            )
            db.execute(
                """INSERT OR REPLACE INTO conversations
                   (id, user_id, title, source, created_at, imported_at, external_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    conversation.id, user.id, conversation.title, conversation.source,
                    _iso(conversation.created_at), conversation.imported_at.isoformat(),
                    conversation.external_id,
                ),
            )
            db.executemany(
                """INSERT OR REPLACE INTO messages
                   (id, conversation_id, user_id, role, content, ordinal, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (m.id, m.conversation_id, m.user_id, m.role.value, m.content, m.ordinal, _iso(m.created_at))
                    for m in imported.messages
                ],
            )

    def upsert(self, chunks: Sequence[ConversationChunk], embeddings: Sequence[Embedding]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("each chunk must have exactly one embedding")
        with self._connection() as db:
            db.executemany(
                """INSERT OR REPLACE INTO chunks
                   (id, conversation_id, user_id, content, ordinal, message_ids, embedding, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        chunk.id, chunk.conversation_id, chunk.user_id, chunk.content, chunk.ordinal,
                        json.dumps(chunk.message_ids), json.dumps(embedding), chunk.created_at.isoformat(),
                    )
                    for chunk, embedding in zip(chunks, embeddings)
                ],
            )

    def search(
        self,
        query_embedding: Embedding,
        *,
        user_id: str,
        limit: int,
        min_similarity: float = 0.0,
    ) -> tuple[RetrievalResult, ...]:
        if limit < 1:
            return ()
        with self._connection() as db:
            rows = db.execute(
                """SELECT ch.id, ch.conversation_id, ch.content, ch.embedding, c.title
                   FROM chunks ch JOIN conversations c
                   ON c.id = ch.conversation_id AND c.user_id = ch.user_id
                   WHERE ch.user_id = ?""",
                (user_id,),
            ).fetchall()
        ranked = []
        seen: set[str] = set()
        for chunk_id, conversation_id, content, raw_embedding, title in rows:
            duplicate_key = " ".join(content.lower().split())
            if duplicate_key in seen:
                continue
            score = _cosine(query_embedding, tuple(json.loads(raw_embedding)))
            if score < min_similarity:
                continue
            seen.add(duplicate_key)
            ranked.append(
                RetrievalResult(content, score, "chunk", chunk_id, conversation_id, title)
            )
        ranked.sort(key=lambda result: (-result.score, result.source_id))
        return tuple(ranked[:limit])

    def delete_conversation(self, conversation_id: str, *, user_id: str) -> None:
        with self._connection() as db:
            db.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )


def _iso(value: object | None) -> str | None:
    return value.isoformat() if value is not None else None  # type: ignore[union-attr]


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("query and stored embeddings have different dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
