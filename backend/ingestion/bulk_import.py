"""Duplicate-aware bulk indexing for normalized ChatGPT exports."""

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from time import monotonic

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chatgpt_export import ChatGPTExportImporter, normalized_fingerprint
from backend.ingestion.chunker import ConversationChunker
from backend.interfaces import EmbeddingService
from backend.models import User
from backend.rag.pipeline import index_conversation
from backend.ingestion.chatgpt_attachments import (
    AttachmentDiscovery, discover_export_attachments, discover_export_directory,
)
from backend.ingestion.pdf_documents import DocumentLimits, PDFDocumentImportService


@dataclass(frozen=True, slots=True)
class BulkImportSummary:
    conversations_found: int
    conversations_imported: int
    conversations_skipped: int
    messages_imported: int
    chunks_indexed: int
    embedding_provider: str
    embedding_model: str
    duration_seconds: float
    errors: tuple[str, ...]
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


class ChatGPTBulkImportService:
    def __init__(
        self,
        *,
        importer: ChatGPTExportImporter,
        chunker: ConversationChunker,
        embeddings: EmbeddingService,
        store: SQLiteVectorStore,
    ) -> None:
        self.importer = importer
        self.chunker = chunker
        self.embeddings = embeddings
        self.store = store

    def import_uploads(
        self,
        uploads: tuple[tuple[str, bytes], ...],
        *,
        user_id: str,
    ) -> BulkImportSummary:
        started = monotonic()
        conversation = self._index_uploads(uploads, user_id=user_id)
        discovery = discover_export_attachments(
            uploads, user_id=user_id,
            known_conversation_ids=conversation[5],
        )
        attachment = self._import_discovery(discovery, user_id=user_id)
        return self._summary(started, conversation, discovery, attachment)

    def import_directory(self, root: Path, *, user_id: str) -> BulkImportSummary:
        """Import an extracted export incrementally while reusing production indexing."""
        started = monotonic()
        shards = sorted(root.glob("conversations-*.json"))
        aggregate = [0, 0, 0, 0, 0]
        errors: list[str] = []
        known_ids: set[str] = set()
        for shard in shards:
            result = self._index_uploads(((shard.name, shard.read_bytes()),), user_id=user_id)
            for index in range(5):
                aggregate[index] += result[index]
            errors.extend(result[6])
            known_ids.update(result[5])
        conversation = (*aggregate, known_ids, errors)
        discovery = discover_export_directory(
            root, user_id=user_id, known_conversation_ids=known_ids
        )
        attachment = self._import_discovery(discovery, user_id=user_id)
        return self._summary(started, conversation, discovery, attachment)

    def _index_uploads(self, uploads: tuple[tuple[str, bytes], ...], *, user_id: str):
        batch = self.importer.import_uploads(uploads, user_id=user_id)
        imported_count = messages = chunks = 0
        skipped = batch.conversations_found - len(batch.conversations)
        errors = [f"conversation input: {error.message}" for error in batch.errors]
        user = User(user_id)
        for imported in batch.conversations:
            fingerprint = normalized_fingerprint(imported)
            existing = self.store.get_import_fingerprint(imported.conversation.id, user_id=user_id)
            if existing == fingerprint:
                skipped += 1
                continue
            try:
                indexed = index_conversation(
                    imported,
                    user=user,
                    chunker=self.chunker,
                    embeddings=self.embeddings,
                    store=self.store,
                    import_fingerprint=fingerprint,
                )
                imported_count += 1
                messages += len(imported.messages)
                chunks += len(indexed)
            except Exception:
                skipped += 1
                errors.append("conversation indexing failed")
        return (
            batch.conversations_found, imported_count, skipped, messages, chunks,
            {item.conversation.id for item in batch.conversations}, errors,
        )

    def _import_discovery(self, discovery: AttachmentDiscovery, *, user_id: str):
        document_limits = DocumentLimits.from_environment()
        pdf_service = PDFDocumentImportService(self.embeddings, self.store, document_limits)
        imported_documents = skipped_documents = document_chunks = 0
        errors: list[str] = []
        attachment_document_ids: dict[str, str] = {}
        resolved_bytes = 0
        for resolved in discovery.resolved_pdfs:
            if resolved_bytes + len(resolved.data) > document_limits.max_total_bytes:
                skipped_documents += 1
                errors.append("resolved PDF assets exceed the aggregate import size limit")
                continue
            resolved_bytes += len(resolved.data)
            summary = pdf_service.import_uploads(
                ((resolved.filename, resolved.data, resolved.conversation_id),), user_id=user_id
            )
            imported_documents += summary.documents_imported
            skipped_documents += summary.documents_skipped
            document_chunks += summary.document_chunks_indexed
            errors.extend(summary.errors)
            document_id = self.store.document_id_for_hash(
                hashlib.sha256(resolved.data).hexdigest(), user_id=user_id
            )
            if document_id:
                attachment_document_ids[resolved.attachment_id] = document_id
        attachment_records = tuple(
            replace(item, document_id=attachment_document_ids.get(item.id))
            for item in discovery.attachments
            if self.store.conversation_exists(item.conversation_id, user_id=user_id)
        )
        attachments_imported = self.store.upsert_attachments(attachment_records)
        return (
            imported_documents, skipped_documents, document_chunks,
            attachments_imported, errors,
        )

    def _summary(self, started, conversation, discovery, attachment) -> BulkImportSummary:
        (
            conversations_found, imported_count, skipped, messages, chunks,
            _known_ids, conversation_errors,
        ) = conversation
        imported_documents, skipped_documents, document_chunks, attachments_imported, attachment_errors = attachment
        return BulkImportSummary(
            conversations_found=conversations_found,
            conversations_imported=imported_count,
            conversations_skipped=skipped,
            messages_imported=messages,
            chunks_indexed=chunks,
            embedding_provider=self.embeddings.provider_name,
            embedding_model=self.embeddings.model_name,
            duration_seconds=round(monotonic() - started, 3),
            errors=tuple((*conversation_errors, *attachment_errors)),
            documents_found=discovery.pdf_references_found,
            documents_imported=imported_documents,
            documents_skipped=skipped_documents,
            document_chunks_indexed=document_chunks,
            document_references_missing=discovery.attachments_missing,
            attachments_found=discovery.attachments_found,
            attachments_imported=attachments_imported,
            pdf_references_found=discovery.pdf_references_found,
            pdf_binaries_resolved=discovery.pdf_binaries_resolved,
            pdf_binaries_indexed=imported_documents,
            attachments_metadata_only=discovery.attachments_metadata_only,
            attachments_ambiguous=discovery.attachments_ambiguous,
            attachments_missing=discovery.attachments_missing,
            attachments_unsupported=discovery.attachments_unsupported,
        )
