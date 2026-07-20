"""Safe local text extraction and chunking for uploaded or export-resolved PDFs."""

from __future__ import annotations

import hashlib
import io
import os
import re
import json
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from time import monotonic
from uuid import NAMESPACE_URL, uuid5

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from backend.database.sqlite_store import SQLiteVectorStore
from backend.interfaces import EmbeddingService
from backend.models import Document, DocumentChunk


class DocumentImportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentLimits:
    max_files: int = 5
    max_file_bytes: int = 20 * 1024 * 1024
    max_total_bytes: int = 50 * 1024 * 1024
    max_pages: int = 300
    max_text_chars: int = 2_000_000
    max_chunks: int = 1000
    chunk_chars: int = 3500
    overlap_chars: int = 300

    def __post_init__(self) -> None:
        values = (
            self.max_files, self.max_file_bytes, self.max_total_bytes, self.max_pages,
            self.max_text_chars, self.max_chunks, self.chunk_chars,
        )
        if min(values) < 1 or not 0 <= self.overlap_chars < self.chunk_chars:
            raise ValueError("PDF import limits must be positive and overlap must be smaller than chunks")

    @classmethod
    def from_environment(cls) -> "DocumentLimits":
        return cls(
            max_files=int(os.environ.get("MEMORA_PDF_MAX_FILES", 5)),
            max_file_bytes=int(os.environ.get("MEMORA_PDF_MAX_FILE_BYTES", 20 * 1024 * 1024)),
            max_total_bytes=int(os.environ.get("MEMORA_PDF_MAX_TOTAL_BYTES", 50 * 1024 * 1024)),
            max_pages=int(os.environ.get("MEMORA_PDF_MAX_PAGES", 300)),
            max_text_chars=int(os.environ.get("MEMORA_PDF_MAX_TEXT_CHARS", 2_000_000)),
            max_chunks=int(os.environ.get("MEMORA_PDF_MAX_CHUNKS", 1000)),
        )


@dataclass(frozen=True, slots=True)
class DocumentImportSummary:
    documents_found: int
    documents_imported: int
    documents_skipped: int
    document_chunks_indexed: int
    embedding_provider: str
    embedding_model: str
    duration_seconds: float
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExportPDFDiscovery:
    references_found: int
    binaries_found: int
    linked_uploads: tuple[tuple[str, bytes, str | None], ...]
    missing_assets: int


def discover_export_pdfs(
    uploads: tuple[tuple[str, bytes], ...], known_conversation_ids: set[str]
) -> ExportPDFDiscovery:
    references: list[tuple[str, str]] = []
    binaries: dict[str, tuple[str, bytes]] = {}
    for filename, data in uploads:
        if not filename.lower().endswith(".zip"):
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for entry in archive.infolist():
                    path = PurePosixPath(entry.filename.replace("\\", "/"))
                    if path.is_absolute() or ".." in path.parts or entry.is_dir():
                        continue
                    if path.suffix.lower() == ".pdf":
                        key = path.name.casefold()
                        if key not in binaries:
                            binaries[key] = (path.name, archive.read(entry))
                    elif path.name in {"conversation_asset_file_names.json", "library_files.json"}:
                        try:
                            metadata = json.loads(archive.read(entry).decode("utf-8-sig"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                        references.extend(_asset_references(metadata, known_conversation_ids))
        except (zipfile.BadZipFile, OSError):
            continue
    linked: list[tuple[str, bytes, str | None]] = []
    missing = 0
    seen: set[tuple[str, str]] = set()
    for conversation_id, raw_name in references:
        name = PurePosixPath(raw_name.replace("\\", "/")).name
        key = (conversation_id, name.casefold())
        binary = binaries.get(name.casefold())
        if key in seen:
            continue
        seen.add(key)
        if binary is None:
            missing += 1
            continue
        linked.append((binary[0], binary[1], conversation_id))
    return ExportPDFDiscovery(len(seen), len(binaries), tuple(linked), missing)


def _asset_references(value: object, known_ids: set[str], parent_key: str | None = None) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        conversation_id = next((value.get(key) for key in ("conversation_id", "conversationId") if isinstance(value.get(key), str)), None)
        filename = next((value.get(key) for key in ("filename", "file_name", "name") if isinstance(value.get(key), str)), None)
        if conversation_id in known_ids and filename and filename.lower().endswith(".pdf"):
            found.append((conversation_id, filename))
        for key, child in value.items():
            if key in known_ids:
                found.extend(_asset_references(child, known_ids, key))
            else:
                found.extend(_asset_references(child, known_ids, parent_key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_asset_references(child, known_ids, parent_key))
    elif isinstance(value, str) and parent_key in known_ids and value.lower().endswith(".pdf"):
        found.append((parent_key, value))
    return found


class PDFDocumentImportService:
    def __init__(self, embeddings: EmbeddingService, store: SQLiteVectorStore, limits: DocumentLimits | None = None) -> None:
        self.embeddings = embeddings
        self.store = store
        self.limits = limits or DocumentLimits.from_environment()

    def import_uploads(
        self,
        uploads: tuple[tuple[str, bytes, str | None], ...],
        *,
        user_id: str,
    ) -> DocumentImportSummary:
        started = monotonic()
        if len(uploads) > self.limits.max_files:
            raise DocumentImportError(f"at most {self.limits.max_files} PDFs may be imported at once")
        if sum(len(data) for _, data, _ in uploads) > self.limits.max_total_bytes:
            raise DocumentImportError("total PDF upload exceeds the size limit")
        imported = skipped = chunk_count = 0
        errors: list[str] = []
        for raw_name, data, parent_id in uploads:
            filename = safe_pdf_filename(raw_name)
            try:
                if parent_id and not self.store.conversation_exists(parent_id, user_id=user_id):
                    raise DocumentImportError("parent conversation was not found for this user")
                if len(data) > self.limits.max_file_bytes:
                    raise DocumentImportError("PDF exceeds the individual file size limit")
                digest = hashlib.sha256(data).hexdigest()
                if self.store.has_document_hash(digest, user_id=user_id):
                    skipped += 1
                    continue
                document, chunks = extract_pdf(filename, data, user_id=user_id, parent_conversation_id=parent_id, limits=self.limits)
                embeddings = tuple(self.embeddings.embed_documents([chunk.content for chunk in chunks]))
                self.store.save_document(document, chunks, embeddings,
                    embedding_provider=self.embeddings.provider_name,
                    embedding_model=self.embeddings.model_name)
                imported += 1
                chunk_count += len(chunks)
            except DocumentImportError as exc:
                skipped += 1
                errors.append(f"{filename}: {exc}")
            except Exception:
                skipped += 1
                errors.append(f"{filename}: PDF import failed")
        return DocumentImportSummary(len(uploads), imported, skipped, chunk_count,
            self.embeddings.provider_name, self.embeddings.model_name,
            round(monotonic() - started, 3), tuple(errors))


def safe_pdf_filename(value: str) -> str:
    name = safe_attachment_filename(value)
    if not name.lower().endswith(".pdf"):
        raise DocumentImportError("only PDF files are supported")
    return name


def safe_attachment_filename(value: str) -> str:
    normalized = value.replace("\\", "/")
    name = PurePosixPath(normalized).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    if not name:
        raise DocumentImportError("attachment filename is invalid")
    return name[:255]


def extract_pdf(
    filename: str,
    data: bytes,
    *,
    user_id: str,
    parent_conversation_id: str | None,
    limits: DocumentLimits,
) -> tuple[Document, tuple[DocumentChunk, ...]]:
    if not data.startswith(b"%PDF-"):
        raise DocumentImportError("file is not a valid PDF")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise DocumentImportError("password-protected PDFs are not supported")
        if len(reader.pages) > limits.max_pages:
            raise DocumentImportError("PDF exceeds the page limit")
        pages = [_normalize_text(page.extract_text() or "") for page in reader.pages]
    except DocumentImportError:
        raise
    except (PdfReadError, ValueError, OSError, KeyError) as exc:
        raise DocumentImportError("PDF is malformed or unsupported") from exc
    if sum(len(text) for text in pages) > limits.max_text_chars:
        raise DocumentImportError("extracted PDF text exceeds the character limit")
    if sum(len(text) for text in pages) < 40:
        raise DocumentImportError("PDF contains no usable extractable text; OCR is not supported")
    digest = hashlib.sha256(data).hexdigest()
    document_id = str(uuid5(NAMESPACE_URL, f"{user_id}:pdf:{digest}"))
    chunks: list[DocumentChunk] = []
    for page_number, text in enumerate(pages, start=1):
        start = 0
        while start < len(text):
            excerpt = text[start:start + limits.chunk_chars].strip()
            if excerpt:
                ordinal = len(chunks)
                chunks.append(DocumentChunk(
                    id=str(uuid5(NAMESPACE_URL, f"{document_id}:{ordinal}:{page_number}")),
                    document_id=document_id, user_id=user_id, filename=filename,
                    parent_conversation_id=parent_conversation_id,
                    page_start=page_number, page_end=page_number,
                    content=excerpt, ordinal=ordinal,
                ))
            if len(chunks) > limits.max_chunks:
                raise DocumentImportError("PDF exceeds the document chunk limit")
            if start + limits.chunk_chars >= len(text):
                break
            start += limits.chunk_chars - limits.overlap_chars
    document = Document(document_id, user_id, filename, digest, parent_conversation_id, len(pages))
    return document, tuple(chunks)


def _normalize_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()
