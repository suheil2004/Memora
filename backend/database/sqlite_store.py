"""SQLite persistence and cosine retrieval for the first vertical slice."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from backend.interfaces import Embedding, ImportedConversation, RetrievalResult
from backend.models import Attachment, AttachmentSource, BinaryResolutionStatus, ConversationChunk, Document, DocumentChunk, User
from backend.rag.reranker import extract_course_codes


class IncompatibleEmbeddingError(ValueError):
    """Stored vectors do not match the active embedding space."""


class SQLiteVectorStore:
    def __init__(self, path: Path | str, *, read_only: bool = False) -> None:
        self.path = str(path)
        self.read_only = read_only
        if not read_only:
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            resolved = Path(self.path).resolve().as_posix()
            return sqlite3.connect(f"file:{quote(resolved, safe='/:')}?mode=ro", uri=True)
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
                    updated_at TEXT, import_fingerprint TEXT,
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
                    embedding TEXT NOT NULL, embedding_provider TEXT NOT NULL,
                    embedding_model TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id, user_id)
                    REFERENCES conversations(id, user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_user ON chunks(user_id);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL, parent_conversation_id TEXT,
                    page_count INTEGER NOT NULL, extraction_status TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    UNIQUE(user_id, content_sha256),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL, user_id TEXT NOT NULL,
                    content TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    page_start INTEGER NOT NULL, page_end INTEGER NOT NULL,
                    embedding TEXT NOT NULL, embedding_provider TEXT NOT NULL,
                    embedding_model TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_document_chunks_user ON document_chunks(user_id);
                CREATE INDEX IF NOT EXISTS idx_documents_user_hash ON documents(user_id, content_sha256);
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                    message_id TEXT NOT NULL, original_filename TEXT NOT NULL, mime_type TEXT,
                    size_bytes INTEGER, library_file_id TEXT, document_id TEXT,
                    binary_resolution_status TEXT NOT NULL, imported_at TEXT NOT NULL,
                    UNIQUE(user_id, conversation_id, message_id, id),
                    FOREIGN KEY (conversation_id, user_id)
                    REFERENCES conversations(id, user_id) ON DELETE CASCADE,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_attachments_user_conversation
                    ON attachments(user_id, conversation_id);
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(chunks)")}
            if "embedding_provider" not in columns:
                db.execute("ALTER TABLE chunks ADD COLUMN embedding_provider TEXT")
                db.execute("UPDATE chunks SET embedding_provider = 'legacy-unknown'")
            if "embedding_model" not in columns:
                db.execute("ALTER TABLE chunks ADD COLUMN embedding_model TEXT")
                db.execute("UPDATE chunks SET embedding_model = 'legacy-unknown'")
            conversation_columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
            if "updated_at" not in conversation_columns:
                db.execute("ALTER TABLE conversations ADD COLUMN updated_at TEXT")
            if "import_fingerprint" not in conversation_columns:
                db.execute("ALTER TABLE conversations ADD COLUMN import_fingerprint TEXT")

    def save_import(
        self,
        user: User,
        imported: ImportedConversation,
        *,
        import_fingerprint: str | None = None,
    ) -> None:
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
                   (id, user_id, title, source, created_at, imported_at, external_id,
                    updated_at, import_fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    conversation.id, user.id, conversation.title, conversation.source,
                    _iso(conversation.created_at), conversation.imported_at.isoformat(),
                    conversation.external_id,
                    _iso(conversation.updated_at), import_fingerprint,
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

    def get_import_fingerprint(self, conversation_id: str, *, user_id: str) -> str | None:
        with self._connection() as db:
            row = db.execute(
                "SELECT import_fingerprint FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
        return row[0] if row else None

    def conversation_exists(self, conversation_id: str, *, user_id: str) -> bool:
        with self._connection() as db:
            return db.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone() is not None

    def validate_embedding_identity(
        self, *, user_id: str, embedding_provider: str, embedding_model: str
    ) -> None:
        with self._connection() as db:
            identities = db.execute(
                """SELECT embedding_provider, embedding_model FROM chunks WHERE user_id = ?
                   UNION SELECT embedding_provider, embedding_model FROM document_chunks
                   WHERE user_id = ?""", (user_id, user_id),
            ).fetchall()
        incompatible = [identity for identity in identities
                        if identity != (embedding_provider, embedding_model)]
        if incompatible:
            raise IncompatibleEmbeddingError(
                "configured embedding provider/model does not match stored vectors"
            )

    def upsert(
        self,
        chunks: Sequence[ConversationChunk],
        embeddings: Sequence[Embedding],
        *,
        embedding_provider: str,
        embedding_model: str,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("each chunk must have exactly one embedding")
        if not embedding_provider.strip() or not embedding_model.strip():
            raise ValueError("embedding provider and model metadata are required")
        with self._connection() as db:
            db.executemany(
                """INSERT OR REPLACE INTO chunks
                   (id, conversation_id, user_id, content, ordinal, message_ids, embedding,
                    embedding_provider, embedding_model, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        chunk.id, chunk.conversation_id, chunk.user_id, chunk.content, chunk.ordinal,
                        json.dumps(chunk.message_ids), json.dumps(embedding), embedding_provider,
                        embedding_model, chunk.created_at.isoformat(),
                    )
                    for chunk, embedding in zip(chunks, embeddings)
                ],
            )

    def has_document_hash(self, content_sha256: str, *, user_id: str) -> bool:
        with self._connection() as db:
            return db.execute(
                "SELECT 1 FROM documents WHERE user_id = ? AND content_sha256 = ?",
                (user_id, content_sha256),
            ).fetchone() is not None

    def document_id_for_hash(self, content_sha256: str, *, user_id: str) -> str | None:
        with self._connection() as db:
            row = db.execute(
                "SELECT id FROM documents WHERE user_id = ? AND content_sha256 = ?",
                (user_id, content_sha256),
            ).fetchone()
        return row[0] if row else None

    def upsert_attachments(self, attachments: Sequence[Attachment]) -> int:
        if not attachments:
            return 0
        if len({item.user_id for item in attachments}) != 1:
            raise ValueError("all attachments must belong to one user")
        with self._connection() as db:
            existing = {
                row[0] for row in db.execute(
                    f"SELECT id FROM attachments WHERE user_id = ? AND id IN ({','.join('?' for _ in attachments)})",
                    (attachments[0].user_id, *(item.id for item in attachments)),
                )
            }
            db.executemany(
                """INSERT INTO attachments
                   (id,user_id,conversation_id,message_id,original_filename,mime_type,
                    size_bytes,library_file_id,document_id,binary_resolution_status,imported_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                    original_filename=excluded.original_filename,
                    mime_type=excluded.mime_type,size_bytes=excluded.size_bytes,
                    library_file_id=coalesce(excluded.library_file_id,attachments.library_file_id),
                    document_id=coalesce(excluded.document_id,attachments.document_id),
                    binary_resolution_status=excluded.binary_resolution_status""",
                [(item.id,item.user_id,item.conversation_id,item.message_id,
                  item.original_filename,item.mime_type,item.size_bytes,item.library_file_id,
                  item.document_id,item.binary_resolution_status.value,item.imported_at.isoformat())
                 for item in attachments],
            )
        return sum(item.id not in existing for item in attachments)

    def attachments_for_conversations(
        self, conversation_ids: Sequence[str], *, user_id: str
    ) -> dict[str, tuple[AttachmentSource, ...]]:
        if not conversation_ids:
            return {}
        placeholders = ",".join("?" for _ in conversation_ids)
        with self._connection() as db:
            rows = db.execute(
                f"""SELECT id,conversation_id,message_id,original_filename,mime_type,
                           binary_resolution_status FROM attachments
                    WHERE user_id = ? AND conversation_id IN ({placeholders})""",
                (user_id, *conversation_ids),
            ).fetchall()
        grouped: dict[str, list[AttachmentSource]] = {}
        for attachment_id, conversation_id, message_id, filename, mime_type, status in rows:
            grouped.setdefault(conversation_id, []).append(AttachmentSource(
                attachment_id, filename, mime_type, conversation_id, message_id,
                BinaryResolutionStatus(status),
            ))
        return {key: tuple(value) for key, value in grouped.items()}

    def save_document(
        self,
        document: Document,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[Embedding],
        *,
        embedding_provider: str,
        embedding_model: str,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("each document chunk must have exactly one embedding")
        with self._connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO users (id, display_name, created_at) VALUES (?, NULL, ?)",
                (document.user_id, document.imported_at.isoformat()),
            )
            db.execute(
                """INSERT INTO documents
                   (id,user_id,filename,content_sha256,parent_conversation_id,page_count,
                    extraction_status,imported_at) VALUES (?,?,?,?,?,?,?,?)""",
                (document.id, document.user_id, document.filename, document.content_sha256,
                 document.parent_conversation_id, document.page_count,
                 document.extraction_status, document.imported_at.isoformat()),
            )
            db.executemany(
                """INSERT INTO document_chunks
                   (id,document_id,user_id,content,ordinal,page_start,page_end,embedding,
                    embedding_provider,embedding_model,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [(chunk.id, chunk.document_id, chunk.user_id, chunk.content, chunk.ordinal,
                  chunk.page_start, chunk.page_end, json.dumps(embedding),
                  embedding_provider, embedding_model, chunk.created_at.isoformat())
                 for chunk, embedding in zip(chunks, embeddings)],
            )

    def search(
        self,
        query_embedding: Embedding,
        *,
        user_id: str,
        limit: int,
        min_similarity: float = 0.0,
        embedding_provider: str,
        embedding_model: str,
    ) -> tuple[RetrievalResult, ...]:
        if limit < 1:
            return ()
        with self._connection() as db:
            identities = db.execute(
                """SELECT embedding_provider, embedding_model FROM chunks WHERE user_id = ?
                   UNION SELECT embedding_provider, embedding_model FROM document_chunks
                   WHERE user_id = ?""",
                (user_id, user_id),
            ).fetchall()
            incompatible = [
                identity for identity in identities
                if identity != (embedding_provider, embedding_model)
            ]
            if incompatible:
                found = ", ".join(f"{provider}/{model}" for provider, model in incompatible)
                raise IncompatibleEmbeddingError(
                    "stored vectors use incompatible embedding metadata "
                    f"({found}); re-index with {embedding_provider}/{embedding_model}"
                )
            rows = db.execute(
                """SELECT ch.id, ch.conversation_id, ch.content, ch.embedding, c.title,
                          ch.user_id, ch.message_ids, ch.created_at
                   FROM chunks ch JOIN conversations c
                   ON c.id = ch.conversation_id AND c.user_id = ch.user_id
                   WHERE ch.user_id = ?""",
                (user_id,),
            ).fetchall()
            document_rows = db.execute(
                """SELECT dc.id, d.parent_conversation_id, dc.content, dc.embedding,
                          d.filename, dc.user_id, d.id, dc.page_start, dc.page_end,
                          dc.created_at, c.title
                   FROM document_chunks dc JOIN documents d ON d.id = dc.document_id
                   LEFT JOIN conversations c ON c.id = d.parent_conversation_id AND c.user_id = d.user_id
                   WHERE dc.user_id = ?""", (user_id,),
            ).fetchall()
        attachment_map = self.attachments_for_conversations(
            tuple({row[1] for row in rows} | {row[1] for row in document_rows if row[1]}),
            user_id=user_id,
        )
        ranked = []
        seen: set[str] = set()
        for (
            chunk_id, conversation_id, content, raw_embedding, title, row_user_id,
            message_ids, conversation_created_at,
        ) in rows:
            duplicate_key = " ".join(content.lower().split())
            if duplicate_key in seen:
                continue
            score = _cosine(query_embedding, tuple(json.loads(raw_embedding)))
            if score < min_similarity:
                continue
            seen.add(duplicate_key)
            ranked.append(
                RetrievalResult(
                    content,
                    score,
                    "chunk",
                    chunk_id,
                    conversation_id,
                    title,
                    row_user_id,
                    tuple(json.loads(message_ids)),
                    _datetime(conversation_created_at),
                    attachment_sources=attachment_map.get(conversation_id, ()),
                )
            )
        for (
            chunk_id, parent_conversation_id, content, raw_embedding, filename,
            row_user_id, document_id, page_start, page_end, imported_at, parent_title,
        ) in document_rows:
            duplicate_key = "document:" + document_id + ":" + " ".join(content.lower().split())
            if duplicate_key in seen:
                continue
            score = _cosine(query_embedding, tuple(json.loads(raw_embedding)))
            if score < min_similarity:
                continue
            seen.add(duplicate_key)
            ranked.append(RetrievalResult(
                content=content, score=score, source_kind="document", source_id=chunk_id,
                conversation_id=parent_conversation_id, conversation_title=parent_title,
                user_id=row_user_id, source_created_at=_datetime(imported_at),
                document_id=document_id, document_filename=filename,
                page_start=page_start, page_end=page_end,
                attachment_sources=attachment_map.get(parent_conversation_id or "", ()),
            ))
        ranked.sort(key=lambda result: (-result.score, result.source_id))
        return tuple(ranked[:limit])

    def delete_conversation(self, conversation_id: str, *, user_id: str) -> None:
        with self._connection() as db:
            db.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )

    def search_course_scope(
        self,
        course_code: str,
        *,
        user_id: str,
        limit: int,
        query_embedding: Embedding | None = None,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
    ) -> tuple[RetrievalResult, ...]:
        """Find chunks belonging to a user-scoped, explicitly identified course.

        SQL first narrows conversation membership. Single-course conversations
        contribute all chunks; ambiguous multi-course conversations contribute
        only chunks explicitly and exclusively tagged with the requested code.
        """
        if limit < 1 or extract_course_codes(course_code) != frozenset({course_code}):
            return ()
        if query_embedding is not None and (not embedding_provider or not embedding_model):
            raise ValueError("embedding metadata is required for scoped semantic ranking")
        department, number = course_code.split()
        variants = tuple(f"%{value.lower()}%" for value in (
            f"{department}{number}", f"{department} {number}", f"{department}-{number}",
        ))
        with self._connection() as db:
            associated_ids = {
                row[0] for row in db.execute(
                    """SELECT id FROM conversations WHERE user_id = ? AND (
                           lower(coalesce(title, '')) LIKE ? OR lower(coalesce(title, '')) LIKE ?
                           OR lower(coalesce(title, '')) LIKE ?)
                       UNION SELECT conversation_id FROM chunks WHERE user_id = ? AND (
                           lower(content) LIKE ? OR lower(content) LIKE ? OR lower(content) LIKE ?)
                       UNION SELECT conversation_id FROM messages WHERE user_id = ? AND (
                           lower(content) LIKE ? OR lower(content) LIKE ? OR lower(content) LIKE ?)""",
                    (user_id, *variants, user_id, *variants, user_id, *variants),
                )
            }
            if not associated_ids:
                return ()
            placeholders = ",".join("?" for _ in associated_ids)
            conversation_rows = db.execute(
                f"""SELECT c.id, c.title, m.content
                    FROM conversations c LEFT JOIN messages m
                    ON m.conversation_id = c.id AND m.user_id = c.user_id
                    WHERE c.user_id = ? AND c.id IN ({placeholders})""",
                (user_id, *associated_ids),
            ).fetchall()
            document_rows = db.execute(
                """SELECT dc.id, d.id, d.filename, d.parent_conversation_id, dc.content,
                          dc.embedding, dc.user_id, dc.page_start, dc.page_end, dc.created_at,
                          dc.embedding_provider, dc.embedding_model, c.title
                   FROM document_chunks dc JOIN documents d ON d.id = dc.document_id
                   LEFT JOIN conversations c ON c.id = d.parent_conversation_id AND c.user_id = d.user_id
                   WHERE dc.user_id = ?""", (user_id,),
            ).fetchall()
            rows = db.execute(
                f"""SELECT ch.id, ch.conversation_id, ch.content, ch.embedding, c.title,
                           ch.user_id, ch.message_ids, ch.created_at,
                           ch.embedding_provider, ch.embedding_model
                    FROM chunks ch JOIN conversations c
                    ON c.id = ch.conversation_id AND c.user_id = ch.user_id
                    WHERE ch.user_id = ? AND ch.conversation_id IN ({placeholders})""",
                (user_id, *associated_ids),
            ).fetchall()
            document_attachment_rows = db.execute(
                """SELECT document_id, conversation_id FROM attachments
                   WHERE user_id = ? AND document_id IS NOT NULL""", (user_id,),
            ).fetchall()
        attachment_map = self.attachments_for_conversations(
            tuple(associated_ids), user_id=user_id
        )
        conversation_codes: dict[str, set[str]] = {}
        conversation_titles: dict[str, str | None] = {}
        document_conversations: dict[str, set[str]] = {}
        for document_id, conversation_id in document_attachment_rows:
            document_conversations.setdefault(document_id, set()).add(conversation_id)
        for conversation_id, title, message_content in conversation_rows:
            conversation_titles[conversation_id] = title
            conversation_codes.setdefault(conversation_id, set()).update(
                extract_course_codes(f"{title or ''}\n{message_content or ''}")
            )
        for row in rows:
            conversation_codes.setdefault(row[1], set()).update(
                extract_course_codes(f"{row[4] or ''}\n{row[2]}")
            )
        matches: list[RetrievalResult] = []
        seen: set[str] = set()
        for (
            chunk_id, conversation_id, content, raw_embedding, title, row_user_id,
            message_ids, created_at, row_provider, row_model,
        ) in rows:
            codes = conversation_codes.get(conversation_id, set())
            chunk_codes = extract_course_codes(content)
            if course_code not in codes:
                continue
            if len(codes) > 1 and chunk_codes != frozenset({course_code}):
                continue
            if query_embedding is not None:
                if (row_provider, row_model) != (embedding_provider, embedding_model):
                    raise IncompatibleEmbeddingError(
                        "stored vectors use incompatible embedding metadata; re-index"
                    )
                score = _cosine(query_embedding, tuple(json.loads(raw_embedding)))
            else:
                score = 1.0
            duplicate_key = " ".join(content.lower().split())
            if duplicate_key in seen:
                continue
            seen.add(duplicate_key)
            matches.append(RetrievalResult(
                content=content,
                score=score,
                source_kind="chunk",
                source_id=chunk_id,
                conversation_id=conversation_id,
                conversation_title=title,
                user_id=row_user_id,
                source_message_ids=tuple(json.loads(message_ids)),
                source_created_at=_datetime(created_at),
                attachment_sources=attachment_map.get(conversation_id, ()),
            ))
        for (
            chunk_id, document_id, filename, parent_id, content, raw_embedding,
            row_user_id, page_start, page_end, imported_at, row_provider, row_model,
            parent_title,
        ) in document_rows:
            explicit_codes = extract_course_codes(content)
            eligible_parents = [
                conversation_id for conversation_id in (
                    ({parent_id} if parent_id else set()) | document_conversations.get(document_id, set())
                ) if course_code in conversation_codes.get(conversation_id, set())
                and len(conversation_codes.get(conversation_id, set())) == 1
            ]
            selected_parent_id = sorted(eligible_parents)[0] if eligible_parents else parent_id
            parent_codes = conversation_codes.get(selected_parent_id or "", set())
            inherited = bool(eligible_parents)
            explicit = explicit_codes == frozenset({course_code})
            if not (inherited or explicit):
                continue
            if len(parent_codes) > 1 and not explicit:
                continue
            if query_embedding is not None:
                if (row_provider, row_model) != (embedding_provider, embedding_model):
                    raise IncompatibleEmbeddingError(
                        "stored vectors use incompatible embedding metadata; re-index"
                    )
                score = _cosine(query_embedding, tuple(json.loads(raw_embedding)))
            else:
                score = 1.0
            matches.append(RetrievalResult(
                content=content, score=score, source_kind="document", source_id=chunk_id,
                conversation_id=selected_parent_id,
                conversation_title=conversation_titles.get(selected_parent_id or "", parent_title),
                user_id=row_user_id,
                source_created_at=_datetime(imported_at), document_id=document_id,
                document_filename=filename, page_start=page_start, page_end=page_end,
                trusted_entity_codes=(course_code,),
                attachment_sources=attachment_map.get(selected_parent_id or "", ()),
            ))
        matches.sort(key=lambda result: (
            -result.score, result.conversation_title or "",
            result.conversation_id or "", result.source_id,
        ))
        return tuple(matches[:limit])


def _iso(value: object | None) -> str | None:
    return value.isoformat() if value is not None else None  # type: ignore[union-attr]


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("query and stored embeddings have different dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
