"""FastAPI entry point for the Memora backend."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.api.schemas import (
    ContextResponse,
    ContextRetrieveRequest,
    ConversationImportRequest,
    ImportResponse,
    RetrievalResultResponse,
)
from backend.api.service import MemoraService
from backend.database.sqlite_store import IncompatibleEmbeddingError, SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import ConversationImportError, JsonConversationImporter
from backend.rag.context_builder import CompactContextBuilder
from backend.rag.openai_embeddings import EmbeddingConfigurationError
from backend.rag.provider import create_embedding_service


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
    )


class ServiceContainer:
    def __init__(self, factory: Callable[[], MemoraService]) -> None:
        self.factory = factory
        self._service: MemoraService | None = None

    def get(self) -> MemoraService:
        if self._service is None:
            self._service = self.factory()
        return self._service


def create_app(*, service_factory: Callable[[], MemoraService] = build_service) -> FastAPI:
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
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    container = ServiceContainer(service_factory)

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

    @application.post("/api/v1/conversations/import", response_model=ImportResponse)
    def import_conversation(request: ConversationImportRequest) -> ImportResponse:
        try:
            payload = request.model_dump(mode="json", exclude={"user_id"})
            summary = service().import_conversation(payload, user_id=request.user_id.strip())
            return ImportResponse.model_validate(asdict(summary))
        except ConversationImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Conversation import failed") from exc

    @application.post("/api/v1/context/retrieve", response_model=ContextResponse)
    def retrieve_context(request: ContextRetrieveRequest) -> ContextResponse:
        try:
            data = service().retrieve_context(
                request.query.strip(),
                user_id=request.user_id.strip(),
                top_k=request.top_k,
                min_similarity=request.min_similarity,
                max_context_chars=request.max_context_chars,
            )
            results = [
                RetrievalResultResponse(
                    user_id=result.user_id or request.user_id,
                    conversation_id=result.conversation_id or "",
                    conversation_title=result.conversation_title,
                    chunk_id=result.source_id,
                    score=result.score,
                    source_message_ids=list(result.source_message_ids),
                )
                for result in data.results
            ]
            return ContextResponse(query=data.query, context=data.context, results=results)
        except IncompatibleEmbeddingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Context retrieval failed") from exc

    return application


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
