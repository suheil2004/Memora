"""Importer for Memora's documented single-conversation JSON format."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.interfaces import ImportedConversation
from backend.models import Conversation, Message, MessageRole, new_id


class ConversationImportError(ValueError):
    """A user-facing error describing an invalid conversation file."""


class JsonConversationImporter:
    def import_file(self, path: Path, *, user_id: str) -> tuple[ImportedConversation, ...]:
        if not user_id.strip():
            raise ConversationImportError("user_id cannot be blank")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConversationImportError(f"conversation file not found: {path}") from exc
        except (OSError, UnicodeError) as exc:
            raise ConversationImportError(f"could not read conversation file: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ConversationImportError(
                f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc

        data = _require_object(raw, "root")
        conversation_id = _required_text(data, "conversation_id")
        title = _optional_text(data, "title")
        created_at = _optional_datetime(data, "created_at")
        raw_messages = data.get("messages")
        if not isinstance(raw_messages, list) or not raw_messages:
            raise ConversationImportError("'messages' must be a non-empty array")

        messages: list[Message] = []
        for ordinal, item in enumerate(raw_messages):
            message = _require_object(item, f"messages[{ordinal}]")
            role_text = _required_text(message, "role", f"messages[{ordinal}]")
            try:
                role = MessageRole(role_text.lower())
            except ValueError as exc:
                allowed = ", ".join(role.value for role in MessageRole)
                raise ConversationImportError(
                    f"messages[{ordinal}].role must be one of: {allowed}"
                ) from exc
            content = _required_text(message, "content", f"messages[{ordinal}]")
            messages.append(
                Message(
                    id=new_id(),
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role=role,
                    content=content.strip(),
                    ordinal=ordinal,
                    created_at=_optional_datetime(message, "created_at", f"messages[{ordinal}]"),
                )
            )

        conversation = Conversation(
            id=conversation_id,
            user_id=user_id,
            source="memora_json_v1",
            title=title,
            created_at=created_at,
            external_id=conversation_id,
        )
        return (ImportedConversation(conversation, tuple(messages)),)


def _require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConversationImportError(f"{location} must be a JSON object")
    return value


def _required_text(data: dict[str, Any], key: str, location: str = "root") -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConversationImportError(f"{location}.{key} must be a non-empty string")
    return value.strip()


def _optional_text(data: dict[str, Any], key: str, location: str = "root") -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConversationImportError(f"{location}.{key} must be a non-empty string when set")
    return value.strip()


def _optional_datetime(
    data: dict[str, Any], key: str, location: str = "root"
) -> datetime | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConversationImportError(f"{location}.{key} must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConversationImportError(f"{location}.{key} must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ConversationImportError(f"{location}.{key} must include a timezone")
    return parsed

