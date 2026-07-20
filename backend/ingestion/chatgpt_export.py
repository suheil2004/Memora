"""Normalize user-supplied ChatGPT export JSON/ZIP files into Memora models."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from backend.interfaces import ImportedConversation
from backend.models import Conversation, Message, MessageRole

MAX_ARCHIVE_FILES = 5_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_JSON_BYTES = 50 * 1024 * 1024
_CONVERSATION_FILE = re.compile(r"^(?:conversations(?:[-_]\d+)?|\d+)\.json$", re.I)


class ChatGPTExportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ChatGPTImportError:
    source: str
    conversation_id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class ChatGPTImportBatch:
    conversations: tuple[ImportedConversation, ...]
    conversations_found: int
    errors: tuple[ChatGPTImportError, ...]


class ChatGPTExportImporter:
    def import_file(self, path: Path, *, user_id: str) -> tuple[ImportedConversation, ...]:
        return self.import_uploads(((path.name, path.read_bytes()),), user_id=user_id).conversations

    def import_uploads(
        self,
        uploads: tuple[tuple[str, bytes], ...],
        *,
        user_id: str,
    ) -> ChatGPTImportBatch:
        if not user_id.strip():
            raise ChatGPTExportError("user_id cannot be blank")
        documents: list[tuple[str, Any]] = []
        errors: list[ChatGPTImportError] = []
        for filename, data in uploads:
            try:
                documents.extend(self._load_upload(filename, data))
            except ChatGPTExportError as exc:
                errors.append(ChatGPTImportError(filename, None, str(exc)))

        raw_conversations: list[tuple[str, Any]] = []
        for source, document in documents:
            if isinstance(document, list):
                raw_conversations.extend((source, item) for item in document)
            elif isinstance(document, dict) and isinstance(document.get("conversations"), list):
                raw_conversations.extend((source, item) for item in document["conversations"])
            else:
                raw_conversations.append((source, document))

        imported: list[ImportedConversation] = []
        for index, (source, raw) in enumerate(raw_conversations):
            conversation_id = _possible_id(raw)
            try:
                imported.append(self._normalize_conversation(raw, user_id=user_id))
            except ChatGPTExportError as exc:
                errors.append(
                    ChatGPTImportError(source, conversation_id, f"conversation {index + 1}: {exc}")
                )
        return ChatGPTImportBatch(tuple(imported), len(raw_conversations), tuple(errors))

    def _load_upload(self, filename: str, data: bytes) -> list[tuple[str, Any]]:
        if filename.lower().endswith(".zip"):
            return self._load_zip(data)
        if not filename.lower().endswith(".json"):
            raise ChatGPTExportError("only JSON and ZIP exports are supported")
        return [(filename, _decode_json(data, filename))]

    def _load_zip(self, data: bytes) -> list[tuple[str, Any]]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, OSError) as exc:
            raise ChatGPTExportError("invalid ZIP export") from exc
        with archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_FILES:
                raise ChatGPTExportError("ZIP export contains too many files")
            max_uncompressed = int(os.environ.get(
                "MEMORA_CHATGPT_MAX_UNCOMPRESSED_BYTES", MAX_ARCHIVE_UNCOMPRESSED_BYTES
            ))
            if sum(entry.file_size for entry in entries) > max_uncompressed:
                raise ChatGPTExportError("ZIP export is too large when uncompressed")
            documents: list[tuple[str, Any]] = []
            for entry in entries:
                path = PurePosixPath(entry.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts:
                    raise ChatGPTExportError("ZIP export contains an unsafe path")
                if entry.is_dir() or not _CONVERSATION_FILE.fullmatch(path.name):
                    continue
                if entry.file_size > MAX_JSON_BYTES:
                    raise ChatGPTExportError("conversation JSON file exceeds the size limit")
                documents.append((entry.filename, _decode_json(archive.read(entry), entry.filename)))
            if not documents:
                raise ChatGPTExportError("ZIP export contains no supported conversation JSON files")
            return documents

    def _normalize_conversation(self, raw: Any, *, user_id: str) -> ImportedConversation:
        if not isinstance(raw, dict):
            raise ChatGPTExportError("conversation must be an object")
        external_id = _text(raw.get("id")) or _text(raw.get("conversation_id"))
        conversation_id = external_id or _derived_conversation_id(raw)
        raw_messages = _active_branch(raw) if isinstance(raw.get("mapping"), dict) else raw.get("messages")
        if not isinstance(raw_messages, list):
            raise ChatGPTExportError("conversation has no supported message graph or list")

        messages: list[Message] = []
        seen_ids: set[str] = set()
        for item in raw_messages:
            parsed = _parse_message(item)
            if parsed is None:
                continue
            external_message_id, role, content, created_at = parsed
            stable_source = external_message_id or f"ordinal:{len(messages)}:{content}"
            message_id = str(uuid5(NAMESPACE_URL, f"{user_id}:{conversation_id}:{stable_source}"))
            if message_id in seen_ids:
                continue
            seen_ids.add(message_id)
            messages.append(
                Message(
                    id=message_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role=role,
                    content=content,
                    ordinal=len(messages),
                    created_at=created_at,
                )
            )
        if not messages:
            raise ChatGPTExportError("conversation contains no supported text messages")
        return ImportedConversation(
            Conversation(
                id=conversation_id,
                user_id=user_id,
                source="chatgpt_export",
                title=_text(raw.get("title")),
                created_at=_timestamp(raw.get("create_time") or raw.get("created_at")),
                external_id=external_id,
                updated_at=_timestamp(raw.get("update_time") or raw.get("updated_at")),
            ),
            tuple(messages),
        )


def _active_branch(conversation: dict[str, Any]) -> list[Any]:
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict):
        return []
    current = _text(conversation.get("current_node"))
    if current not in mapping:
        leaves = [
            (node_id, node) for node_id, node in mapping.items()
            if isinstance(node, dict) and not node.get("children")
        ]
        current = max(leaves, key=lambda pair: _node_time(pair[1]), default=(None, None))[0]
    branch: list[Any] = []
    visited: set[str] = set()
    while isinstance(current, str) and current in mapping and current not in visited:
        visited.add(current)
        node = mapping[current]
        if not isinstance(node, dict):
            break
        if node.get("message") is not None:
            branch.append(node["message"])
        current = _text(node.get("parent"))
    branch.reverse()
    return branch


def _parse_message(raw: Any) -> tuple[str | None, MessageRole, str, datetime | None] | None:
    if not isinstance(raw, dict):
        return None
    author = raw.get("author")
    role_value = author.get("role") if isinstance(author, dict) else raw.get("role")
    if role_value not in ("user", "assistant"):
        return None
    content = raw.get("content", raw.get("text"))
    text = _content_text(content)
    if not text:
        return None
    return _text(raw.get("id")), MessageRole(role_value), text, _timestamp(raw.get("create_time"))


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content.strip() or None
    if not isinstance(content, dict):
        return None
    if content.get("content_type") not in (None, "text", "multimodal_text"):
        return None
    parts = content.get("parts")
    if not isinstance(parts, list):
        return None
    strings = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
    return "\n".join(strings) or None


def normalized_fingerprint(imported: ImportedConversation) -> str:
    payload = {
        "id": imported.conversation.id,
        "title": imported.conversation.title,
        "updated_at": _datetime_text(imported.conversation.updated_at),
        "messages": [
            {"role": message.role.value, "content": message.content, "created_at": _datetime_text(message.created_at)}
            for message in imported.messages
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _decode_json(data: bytes, source: str) -> Any:
    if len(data) > MAX_JSON_BYTES:
        raise ChatGPTExportError("conversation JSON file exceeds the size limit")
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChatGPTExportError(f"invalid JSON in {Path(source).name}") from exc


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _node_time(node: Any) -> float:
    if not isinstance(node, dict) or not isinstance(node.get("message"), dict):
        return float("-inf")
    value = node["message"].get("create_time")
    return float(value) if isinstance(value, (int, float)) else float("-inf")


def _possible_id(raw: Any) -> str | None:
    return _text(raw.get("id") or raw.get("conversation_id")) if isinstance(raw, dict) else None


def _derived_conversation_id(raw: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()[:24]
    return f"chatgpt-{digest}"


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
