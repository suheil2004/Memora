"""FastAPI entry point for the Memora backend."""

from __future__ import annotations

import os
import logging
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.schemas import (
    AttachmentMemorySourceResponse,
    ContextResponse,
    BulkImportResponse,
    ContextRetrieveRequest,
    ConversationImportRequest,
    ImportResponse,
    MemoryBriefResponse,
    MemorySourceResponse,
    DocumentMemorySourceResponse,
    DocumentImportResponse,
    MemoryClearResponse,
    MemoryStatisticsResponse,
    RetrievalResultResponse,
)
from backend.api.service import MemoraService
from backend.api.security import (
    InMemoryRateLimiter,
    LocalSecurityConfig,
    enforce_rate_limit,
)
from backend.database.sqlite_store import IncompatibleEmbeddingError, SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import ConversationImportError, JsonConversationImporter
from backend.ingestion.chatgpt_export import ChatGPTExportError
from backend.rag.context_builder import CompactContextBuilder
from backend.rag.openai_embeddings import EmbeddingConfigurationError
from backend.rag.provider import create_embedding_service
from backend.rag.synthesis import create_memory_synthesizer
from backend.rag.memory_facts import create_memory_fact_extractor
from backend.ingestion.pdf_documents import DocumentImportError, DocumentLimits


_MAX_VALIDATION_ERRORS = 10
_MAX_VALIDATION_LOCATION_PARTS = 8
_MAX_VALIDATION_LOCATION_CHARS = 64
_MAX_VALIDATION_TYPE_CHARS = 64
_MAX_VALIDATION_MESSAGE_CHARS = 160
_LOGGER = logging.getLogger(__name__)


def build_service() -> MemoraService:
    database_path = _database_path(os.environ.get("MEMORA_DATABASE_URL", "sqlite:///./memora.sqlite3"))
    return MemoraService(
        importer=JsonConversationImporter(),
        chunker=ConversationChunker(
            max_tokens=_positive_int("MEMORA_CHUNK_SIZE_TOKENS", 400),
            overlap_tokens=_nonnegative_int("MEMORA_CHUNK_OVERLAP_TOKENS", 50),
        ),
        embeddings=create_embedding_service(),
        store=SQLiteVectorStore(database_path),
        context_builder=CompactContextBuilder(),
        context_max_chars=_positive_int("MEMORA_CONTEXT_MAX_CHARS", 6000),
        synthesizer=create_memory_synthesizer(),
        fact_extractor=create_memory_fact_extractor(),
    )


class ServiceContainer:
    def __init__(self, factory: Callable[[], MemoraService]) -> None:
        self.factory = factory
        self._service: MemoraService | None = None

    def get(self) -> MemoraService:
        if self._service is None:
            self._service = self.factory()
        return self._service


def create_app(
    *,
    service_factory: Callable[[], MemoraService] = build_service,
    security_config: LocalSecurityConfig | None = None,
    rate_limiter: InMemoryRateLimiter | None = None,
) -> FastAPI:
    application = FastAPI(title="Memora API", version="1.0.0")
    origins = [
        origin.strip()
        for origin in os.environ.get(
            "MEMORA_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    container = ServiceContainer(service_factory)
    security = security_config or LocalSecurityConfig.from_environment()
    limiter = rate_limiter or InMemoryRateLimiter()

    @application.exception_handler(RequestValidationError)
    async def sanitized_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [_sanitize_validation_error(error) for error in exc.errors()[:_MAX_VALIDATION_ERRORS]]
        return JSONResponse(status_code=422, content={"detail": errors})

    def service() -> MemoraService:
        try:
            return container.get()
        except EmbeddingConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Memora service configuration is invalid") from exc

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "memora"}

    @application.get("/api/v1/memory/stats", response_model=MemoryStatisticsResponse)
    def memory_statistics(
        authorization: Annotated[list[str] | None, Header()] = None,
    ) -> MemoryStatisticsResponse:
        user_id = security.authenticate(authorization)
        try:
            response = MemoryStatisticsResponse.model_validate(
                asdict(service().memory_statistics(user_id=user_id))
            )
            _LOGGER.info("memory_stats completed")
            return response
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Memory statistics failed") from exc

    @application.delete("/api/v1/memory", response_model=MemoryClearResponse)
    async def clear_memory(
        request: Request,
        authorization: Annotated[list[str] | None, Header()] = None,
    ) -> MemoryClearResponse:
        user_id = security.authenticate(authorization)
        if "user_id" in request.query_params or (await request.body()).strip():
            raise HTTPException(status_code=422, detail="This endpoint does not accept request data")
        try:
            summary = service().clear_memory(user_id=user_id)
            _LOGGER.info("memory_clear completed rows_deleted=%d", summary.rows_deleted)
            return MemoryClearResponse(cleared=True, rows_deleted=summary.rows_deleted)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Memory deletion failed") from exc

    @application.post("/api/v1/conversations/import", response_model=ImportResponse)
    def import_conversation(
        request: ConversationImportRequest,
        authorization: Annotated[list[str] | None, Header()] = None,
    ) -> ImportResponse:
        user_id = security.authenticate(authorization)
        enforce_rate_limit(
            limiter,
            f"{user_id}:import",
            limit=security.import_limit,
            window_seconds=security.import_window_seconds,
        )
        try:
            payload = request.model_dump(mode="json")
            summary = service().import_conversation(payload, user_id=user_id)
            return ImportResponse.model_validate(asdict(summary))
        except ConversationImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Conversation import failed") from exc

    @application.post("/api/v1/context/retrieve", response_model=ContextResponse)
    def retrieve_context(
        request: ContextRetrieveRequest,
        authorization: Annotated[list[str] | None, Header()] = None,
    ) -> ContextResponse:
        user_id = security.authenticate(authorization)
        enforce_rate_limit(
            limiter,
            f"{user_id}:retrieve",
            limit=security.retrieval_limit,
            window_seconds=security.retrieval_window_seconds,
        )
        try:
            data = service().retrieve_context(
                request.query.strip(),
                user_id=user_id,
                top_k=request.top_k,
                min_similarity=request.min_similarity,
                max_context_chars=request.max_context_chars,
            )
            results = [
                RetrievalResultResponse(
                    user_id=result.user_id or user_id,
                    conversation_id=result.conversation_id or "",
                    conversation_title=result.conversation_title,
                    chunk_id=result.source_id,
                    score=result.score,
                    source_message_ids=list(result.source_message_ids),
                )
                for result in data.results
            ]
            memories = [
                MemoryBriefResponse(
                    thread_id=brief.thread_id,
                    title=brief.title,
                    subject=brief.subject,
                    summary=brief.summary,
                    key_details=list(brief.key_details),
                    sources=[
                        MemorySourceResponse(
                            conversation_id=conversation_id,
                            conversation_title=title,
                        )
                        for conversation_id, title in zip(
                            brief.source_conversation_ids, brief.sources, strict=True
                        )
                    ] + [
                        DocumentMemorySourceResponse(
                            document_id=source.document_id,
                            filename=source.filename,
                            page_start=source.page_start,
                            page_end=source.page_end,
                            parent_conversation_id=source.parent_conversation_id,
                        )
                        for source in brief.document_sources
                    ] + [
                        AttachmentMemorySourceResponse(
                            attachment_id=source.attachment_id,
                            filename=source.filename,
                            mime_type=source.mime_type,
                            conversation_id=source.conversation_id,
                            message_id=source.message_id,
                            binary_resolution_status=source.binary_resolution_status.value,
                        )
                        for source in brief.attachment_sources
                    ],
                    used_fallback=brief.used_fallback,
                    latest_timestamp=brief.latest_timestamp,
                )
                for brief in data.briefs
            ]
            return ContextResponse(
                query=data.query,
                context=data.context,
                results=results,
                memories=memories,
            )
        except IncompatibleEmbeddingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Context retrieval failed") from exc

    @application.post("/api/v1/import/chatgpt", response_model=BulkImportResponse)
    async def import_chatgpt(
        files: list[UploadFile] = File(...),
        authorization: Annotated[list[str] | None, Header()] = None,
    ) -> BulkImportResponse:
        user_id = security.authenticate(authorization)
        if not files:
            raise HTTPException(status_code=422, detail="at least one export file is required")
        if len(files) > 10:
            raise HTTPException(status_code=422, detail="at most 10 export files may be imported at once")
        enforce_rate_limit(
            limiter,
            f"{user_id}:import",
            limit=security.import_limit,
            window_seconds=security.import_window_seconds,
        )
        uploads: list[tuple[str, bytes]] = []
        total_bytes = 0
        max_upload_bytes = int(os.environ.get(
            "MEMORA_CHATGPT_MAX_UPLOAD_BYTES", 250 * 1024 * 1024
        ))
        try:
            for upload in files:
                remaining_bytes = max_upload_bytes - total_bytes
                data = await upload.read(remaining_bytes + 1)
                total_bytes += len(data)
                if total_bytes > max_upload_bytes:
                    raise HTTPException(status_code=413, detail="uploaded export exceeds the size limit")
                uploads.append((upload.filename or "upload", data))
            summary = service().import_chatgpt_history(tuple(uploads), user_id=user_id)
            return BulkImportResponse.model_validate(asdict(summary))
        except ChatGPTExportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="ChatGPT history import failed") from exc
        finally:
            for upload in files:
                await upload.close()

    @application.post("/api/v1/import/documents", response_model=DocumentImportResponse)
    async def import_documents(
        files: list[UploadFile] = File(...),
        parent_conversation_id: str | None = None,
        authorization: Annotated[list[str] | None, Header()] = None,
    ) -> DocumentImportResponse:
        user_id = security.authenticate(authorization)
        limits = DocumentLimits.from_environment()
        if not files:
            raise HTTPException(status_code=422, detail="at least one PDF is required")
        if len(files) > limits.max_files:
            raise HTTPException(status_code=422, detail=f"at most {limits.max_files} PDFs may be imported at once")
        enforce_rate_limit(
            limiter, f"{user_id}:import", limit=security.import_limit,
            window_seconds=security.import_window_seconds,
        )
        uploads: list[tuple[str, bytes, str | None]] = []
        total_bytes = 0
        try:
            for upload in files:
                data = await upload.read(limits.max_file_bytes + 1)
                if len(data) > limits.max_file_bytes:
                    raise HTTPException(status_code=413, detail="PDF exceeds the individual file size limit")
                total_bytes += len(data)
                if total_bytes > limits.max_total_bytes:
                    raise HTTPException(status_code=413, detail="total PDF upload exceeds the size limit")
                uploads.append((upload.filename or "document.pdf", data, parent_conversation_id))
            summary = service().import_documents(tuple(uploads), user_id=user_id)
            return DocumentImportResponse.model_validate(asdict(summary))
        except DocumentImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Document import failed") from exc
        finally:
            for upload in files:
                await upload.close()

    return application


def _sanitize_validation_error(error: dict[str, object]) -> dict[str, object]:
    raw_location = error.get("loc")
    location_parts = raw_location if isinstance(raw_location, (list, tuple)) else ()
    location: list[str | int] = []
    for part in location_parts[:_MAX_VALIDATION_LOCATION_PARTS]:
        if isinstance(part, int):
            location.append(part)
        else:
            location.append(str(part)[:_MAX_VALIDATION_LOCATION_CHARS])

    return {
        "loc": location,
        "type": str(error.get("type", "validation_error"))[:_MAX_VALIDATION_TYPE_CHARS],
        "msg": str(error.get("msg", "Invalid request"))[:_MAX_VALIDATION_MESSAGE_CHARS],
    }


def _database_path(url: str) -> Path:
    prefix = "sqlite:///"
    if not url.startswith(prefix) or not url[len(prefix):]:
        raise ValueError("MEMORA_DATABASE_URL must use sqlite:///path")
    return Path(url[len(prefix):])


def _positive_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


app = create_app()
