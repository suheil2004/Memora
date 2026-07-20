"""Import an already-extracted ChatGPT export into the configured Memora database."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

from backend.database.sqlite_store import IncompatibleEmbeddingError, SQLiteVectorStore
from backend.ingestion.bulk_import import BulkImportSummary, ChatGPTBulkImportService
from backend.ingestion.chatgpt_export import ChatGPTExportImporter
from backend.ingestion.chunker import ConversationChunker
from backend.rag.openai_embeddings import EmbeddingConfigurationError
from backend.rag.provider import create_embedding_service


_REQUIRED_METADATA = (
    "conversation_asset_file_names.json", "library_files.json", "export_manifest.json",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        root = _validate_export_directory(args.export_directory)
        database_url = _required_environment("MEMORA_DATABASE_URL")
        user_id = _required_environment("MEMORA_USER_ID")
        provider = _required_environment("MEMORA_EMBEDDING_PROVIDER")
        database_path = _database_path(database_url)
        embeddings = create_embedding_service(provider)
        store = SQLiteVectorStore(database_path)
        store.validate_embedding_identity(
            user_id=user_id, embedding_provider=embeddings.provider_name,
            embedding_model=embeddings.model_name,
        )
        service = ChatGPTBulkImportService(
            importer=ChatGPTExportImporter(),
            chunker=ConversationChunker(
                max_tokens=_positive_int("MEMORA_CHUNK_SIZE_TOKENS", 400),
                overlap_tokens=_nonnegative_int("MEMORA_CHUNK_OVERLAP_TOKENS", 50),
            ),
            embeddings=embeddings,
            store=store,
        )
        summary = service.import_directory(root, user_id=user_id)
    except (ValueError, OSError, EmbeddingConfigurationError, IncompatibleEmbeddingError) as exc:
        print(_safe_fatal_message(exc), file=sys.stderr)
        return 1
    _print_summary(summary)
    return 0


def _validate_export_directory(value: Path) -> Path:
    if not value.exists():
        raise ValueError("Export directory does not exist.")
    if not value.is_dir():
        raise ValueError("Export path must be a directory.")
    root = value.resolve(strict=True)
    shards = list(root.glob("conversations-*.json"))
    if not shards:
        raise ValueError("Directory contains no numbered ChatGPT conversation shards.")
    required = [root / name for name in _REQUIRED_METADATA]
    if any(not path.is_file() for path in required):
        raise ValueError("Directory is missing required ChatGPT attachment metadata.")
    if any(path.is_symlink() or not path.resolve(strict=True).is_relative_to(root)
           for path in (*shards, *required)):
        raise ValueError("Directory contains an unsafe metadata path.")
    return root


def _database_path(url: str) -> Path:
    prefix = "sqlite:///"
    if not url.startswith(prefix) or not url[len(prefix):]:
        raise ValueError("MEMORA_DATABASE_URL must use sqlite:///path.")
    return Path(url[len(prefix):])


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required.")
    return value


def _positive_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError(f"{name} must be positive.")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value < 0:
        raise ValueError(f"{name} cannot be negative.")
    return value


def _print_summary(summary: BulkImportSummary) -> None:
    values = (
        ("Conversations found", summary.conversations_found),
        ("Conversations imported", summary.conversations_imported),
        ("Conversations skipped", summary.conversations_skipped),
        ("Attachments found", summary.attachments_found),
        ("Attachments imported", summary.attachments_imported),
        ("PDF references found", summary.pdf_references_found),
        ("PDF binaries resolved", summary.pdf_binaries_resolved),
        ("PDF binaries indexed", summary.pdf_binaries_indexed),
        ("Metadata-only attachments", summary.attachments_metadata_only),
        ("Ambiguous attachments", summary.attachments_ambiguous),
        ("Missing attachments", summary.attachments_missing),
        ("Unsupported attachments", summary.attachments_unsupported),
        ("Document chunks indexed", summary.document_chunks_indexed),
    )
    for label, value in values:
        print(f"{label}: {value}")
    categories = _error_categories(summary.errors)
    if categories:
        print("Safe error categories: " + ", ".join(
            f"{name}={count}" for name, count in sorted(categories.items())
        ))
    print(f"Duration: {summary.duration_seconds:.3f}s")


def _error_categories(errors: tuple[str, ...]) -> Counter[str]:
    categories: Counter[str] = Counter()
    patterns = (
        ("encrypted_pdf", r"password-protected|encrypted"),
        ("malformed_pdf", r"malformed|invalid pdf"),
        ("no_extractable_text", r"no usable extractable text|ocr"),
        ("size_limit", r"size limit|too large"),
        ("page_limit", r"page limit"),
        ("chunk_limit", r"chunk limit"),
        ("conversation", r"conversation"),
    )
    for error in errors:
        category = next((name for name, pattern in patterns if re.search(pattern, error, re.I)), "other")
        categories[category] += 1
    return categories


def _safe_fatal_message(exc: Exception) -> str:
    message = str(exc)
    allowed_prefixes = (
        "Export ", "Directory ", "MEMORA_", "OPENAI_", "configured embedding",
        "unsupported embedding", "the 'openai' package",
    )
    return message if message.startswith(allowed_prefixes) else "Import could not start due to invalid configuration."


if __name__ == "__main__":
    raise SystemExit(main())
