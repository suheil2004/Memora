"""HTTP request and response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MessageInput(StrictModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(min_length=1)
    created_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content cannot be blank")
        return value


class ConversationImportRequest(StrictModel):
    user_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    title: str | None = None
    created_at: datetime | None = None
    messages: list[MessageInput] = Field(min_length=1)

    @field_validator("user_id", "conversation_id")
    @classmethod
    def identifiers_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value


class ImportResponse(StrictModel):
    conversation_id: str
    title: str | None
    chunks_indexed: int
    embedding_provider: str
    embedding_model: str


class ContextRetrieveRequest(StrictModel):
    user_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    min_similarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    max_context_chars: int | None = Field(default=None, ge=64, le=50000)

    @field_validator("user_id", "query")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value


class RetrievalResultResponse(StrictModel):
    user_id: str
    conversation_id: str
    conversation_title: str | None
    chunk_id: str
    score: float
    source_message_ids: list[str]


class ContextResponse(StrictModel):
    query: str
    context: str
    results: list[RetrievalResultResponse]


class BulkImportResponse(StrictModel):
    conversations_found: int
    conversations_imported: int
    conversations_skipped: int
    messages_imported: int
    chunks_indexed: int
    embedding_provider: str
    embedding_model: str
    duration_seconds: float
    errors: list[str]
