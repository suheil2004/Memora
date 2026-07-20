"""HTTP request and response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MessageInput(StrictModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(min_length=1, max_length=20000)
    created_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content cannot be blank")
        return value


class ConversationImportRequest(StrictModel):
    conversation_id: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=500)
    created_at: datetime | None = None
    messages: list[MessageInput] = Field(min_length=1, max_length=500)

    @field_validator("conversation_id")
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
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)
    min_similarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    max_context_chars: int | None = Field(default=None, ge=64, le=50000)

    @field_validator("query")
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


class MemorySourceResponse(StrictModel):
    type: Literal["conversation"] = "conversation"
    conversation_id: str
    conversation_title: str


class DocumentMemorySourceResponse(StrictModel):
    type: Literal["document"] = "document"
    document_id: str
    filename: str
    page_start: int
    page_end: int
    parent_conversation_id: str | None


class AttachmentMemorySourceResponse(StrictModel):
    type: Literal["attachment"] = "attachment"
    attachment_id: str
    filename: str
    mime_type: str | None
    conversation_id: str
    message_id: str
    binary_resolution_status: Literal["resolved", "metadata_only", "ambiguous", "missing", "unsupported"]


class MemoryBriefResponse(StrictModel):
    thread_id: str
    title: str
    subject: str
    summary: str
    key_details: list[str]
    sources: list[MemorySourceResponse | DocumentMemorySourceResponse | AttachmentMemorySourceResponse]
    used_fallback: bool
    latest_timestamp: datetime | None = None


class ContextResponse(StrictModel):
    query: str
    context: str
    results: list[RetrievalResultResponse]
    memories: list[MemoryBriefResponse]


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
    documents_found: int = 0
    documents_imported: int = 0
    documents_skipped: int = 0
    document_chunks_indexed: int = 0
    document_references_missing: int = 0
    attachments_found: int = 0
    attachments_imported: int = 0
    pdf_references_found: int = 0
    pdf_binaries_resolved: int = 0
    pdf_binaries_indexed: int = 0
    attachments_metadata_only: int = 0
    attachments_ambiguous: int = 0
    attachments_missing: int = 0
    attachments_unsupported: int = 0


class DocumentImportResponse(StrictModel):
    documents_found: int
    documents_imported: int
    documents_skipped: int
    document_chunks_indexed: int
    embedding_provider: str
    embedding_model: str
    duration_seconds: float
    errors: list[str]
