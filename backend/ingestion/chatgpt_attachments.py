"""Conservative attachment discovery for the observed ChatGPT export schema."""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, uuid5

from backend.models import Attachment, BinaryResolutionStatus
from backend.ingestion.pdf_documents import safe_attachment_filename


_SUPPORTED_IDENTIFIER_KEYS = frozenset({
    "id", "file_id",
    "initiating_conversation_id", "origination_thread_id", "origination_message_id",
})


@dataclass(frozen=True, slots=True)
class ResolvedPDF:
    attachment_id: str
    filename: str
    data: bytes
    conversation_id: str


@dataclass(frozen=True, slots=True)
class AttachmentDiscovery:
    attachments: tuple[Attachment, ...]
    resolved_pdfs: tuple[ResolvedPDF, ...]
    attachments_found: int
    pdf_references_found: int
    pdf_binaries_resolved: int
    attachments_metadata_only: int
    attachments_ambiguous: int
    attachments_missing: int
    attachments_unsupported: int


class _Entry(Protocol):
    filename: str

    def is_dir(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class _DirectoryEntry:
    filename: str
    path: Path

    def is_dir(self) -> bool:
        return False


def discover_export_attachments(
    uploads: tuple[tuple[str, bytes], ...], *, user_id: str, known_conversation_ids: set[str]
) -> AttachmentDiscovery:
    records: list[Attachment] = []
    resolved: list[ResolvedPDF] = []
    for upload_name, upload_data in uploads:
        if not upload_name.lower().endswith(".zip"):
            continue
        records_part, resolved_part = _discover_zip(
            upload_data, user_id=user_id, known_conversation_ids=known_conversation_ids
        )
        records.extend(records_part)
        resolved.extend(resolved_part)
    unique_records = tuple({item.id: item for item in records}.values())
    unique_resolved = tuple({item.attachment_id: item for item in resolved}.values())
    statuses = [item.binary_resolution_status for item in unique_records]
    return AttachmentDiscovery(
        unique_records, unique_resolved, len(unique_records),
        sum(_is_pdf(item.original_filename, item.mime_type) for item in unique_records),
        len(unique_resolved), statuses.count(BinaryResolutionStatus.METADATA_ONLY),
        statuses.count(BinaryResolutionStatus.AMBIGUOUS),
        statuses.count(BinaryResolutionStatus.MISSING),
        statuses.count(BinaryResolutionStatus.UNSUPPORTED),
    )


def discover_export_directory(
    root: Path, *, user_id: str, known_conversation_ids: set[str]
) -> AttachmentDiscovery:
    """Resolve an extracted export without constructing an in-memory archive."""
    resolved_root = root.resolve(strict=True)
    entries: list[_DirectoryEntry] = []
    for candidate in resolved_root.rglob("*"):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(resolved_root):
            continue
        entries.append(_DirectoryEntry(resolved.relative_to(resolved_root).as_posix(), resolved))

    def read(entry: _Entry) -> bytes:
        if not isinstance(entry, _DirectoryEntry):
            raise OSError("invalid directory entry")
        resolved = entry.path.resolve(strict=True)
        if not resolved.is_relative_to(resolved_root):
            raise OSError("asset path escapes export directory")
        return resolved.read_bytes()

    records, pdfs = _discover_entries(
        entries, read, user_id=user_id,
        known_conversation_ids=known_conversation_ids,
    )
    return _summarize(records, pdfs)


def _discover_zip(
    data: bytes, *, user_id: str, known_conversation_ids: set[str]
) -> tuple[list[Attachment], list[ResolvedPDF]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError):
        return [], []
    with archive:
        return _discover_entries(
            archive.infolist(), archive.read, user_id=user_id,
            known_conversation_ids=known_conversation_ids,
        )


def _discover_entries(
    source_entries: list[_Entry], read: Callable[[_Entry], bytes], *,
    user_id: str, known_conversation_ids: set[str],
) -> tuple[list[Attachment], list[ResolvedPDF]]:
        entries: dict[str, _Entry] = {}
        metadata: dict[str, object] = {}
        raw_attachments: list[dict] = []
        for entry in source_entries:
            path = PurePosixPath(entry.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or entry.is_dir():
                continue
            entries[path.as_posix()] = entry
            if path.name in {
                "conversation_asset_file_names.json", "library_files.json", "export_manifest.json",
            } or re.fullmatch(r"conversations(?:[-_]\d+)?\.json", path.name, re.I):
                try:
                    decoded = json.loads(read(entry).decode("utf-8-sig"))
                    if re.fullmatch(r"conversations(?:[-_]\d+)?\.json", path.name, re.I):
                        raw_attachments.extend(_message_attachments(
                            {path.name: decoded}, known_conversation_ids, user_id
                        ))
                    else:
                        metadata[path.name] = decoded
                except (UnicodeDecodeError, json.JSONDecodeError, OSError):
                    continue
        asset_names = metadata.get("conversation_asset_file_names.json")
        asset_names = asset_names if isinstance(asset_names, dict) else {}
        library = metadata.get("library_files.json")
        library = library if isinstance(library, list) else []
        manifest = metadata.get("export_manifest.json")
        logical = manifest.get("logical_files", {}) if isinstance(manifest, dict) else {}
        records: list[Attachment] = []
        resolved: list[ResolvedPDF] = []
        for raw in raw_attachments:
            filename = safe_attachment_filename(raw["name"])
            library_matches = _library_matches(raw, library)
            library_record = library_matches[0] if len(library_matches) == 1 else None
            candidate_paths = _candidate_paths(raw, library_record, asset_names, logical, entries)
            is_pdf = _is_pdf(filename, raw.get("mime_type"))
            if not is_pdf:
                status = BinaryResolutionStatus.UNSUPPORTED
            elif len(library_matches) > 1 or len(candidate_paths) > 1:
                status = BinaryResolutionStatus.AMBIGUOUS
            elif not candidate_paths:
                status = BinaryResolutionStatus.METADATA_ONLY
            else:
                try:
                    binary = read(entries[candidate_paths[0]])
                except (KeyError, OSError):
                    status = BinaryResolutionStatus.MISSING
                else:
                    status = (
                        BinaryResolutionStatus.RESOLVED
                        if binary.startswith(b"%PDF-") else BinaryResolutionStatus.UNSUPPORTED
                    )
            attachment_id = str(uuid5(
                NAMESPACE_URL,
                f"{user_id}:attachment:{raw['conversation_id']}:{raw['message_id']}:{raw['stable_id']}:{filename}",
            ))
            library_id = _library_id(library_record)
            record = Attachment(
                attachment_id, user_id, raw["conversation_id"], raw["message_id"], filename,
                raw.get("mime_type"), raw.get("size"), library_id, None, status,
            )
            records.append(record)
            if status == BinaryResolutionStatus.RESOLVED:
                resolved.append(ResolvedPDF(
                    attachment_id, filename, binary, raw["conversation_id"]
                ))
        return records, resolved


def _summarize(records: list[Attachment], pdfs: list[ResolvedPDF]) -> AttachmentDiscovery:
    unique_records = tuple({item.id: item for item in records}.values())
    unique_pdfs = tuple({item.attachment_id: item for item in pdfs}.values())
    statuses = [item.binary_resolution_status for item in unique_records]
    return AttachmentDiscovery(
        unique_records, unique_pdfs, len(unique_records),
        sum(_is_pdf(item.original_filename, item.mime_type) for item in unique_records),
        len(unique_pdfs), statuses.count(BinaryResolutionStatus.METADATA_ONLY),
        statuses.count(BinaryResolutionStatus.AMBIGUOUS),
        statuses.count(BinaryResolutionStatus.MISSING),
        statuses.count(BinaryResolutionStatus.UNSUPPORTED),
    )


def _message_attachments(
    metadata: dict[str, object], known_ids: set[str], user_id: str
) -> list[dict]:
    found: list[dict] = []
    for name, value in metadata.items():
        if not re.fullmatch(r"conversations(?:[-_]\d+)?\.json", name, re.I):
            continue
        conversations = value if isinstance(value, list) else []
        for conversation in conversations:
            if not isinstance(conversation, dict):
                continue
            conversation_id = next((candidate for candidate in (
                *_normalize_identifier_candidates(conversation.get("id")),
                *_normalize_identifier_candidates(conversation.get("conversation_id")),
            ) if candidate in known_ids), None)
            if conversation_id is None:
                continue
            mapping = conversation.get("mapping")
            messages = [node.get("message") for node in mapping.values() if isinstance(node, dict)] if isinstance(mapping, dict) else conversation.get("messages", [])
            for message in messages if isinstance(messages, list) else []:
                if not isinstance(message, dict):
                    continue
                source_message_id = next(iter(_normalize_identifier_candidates(message.get("id"))), None)
                attachment_values = message.get("metadata", {}).get("attachments", []) if isinstance(message.get("metadata"), dict) else []
                for item in attachment_values if isinstance(attachment_values, list) else []:
                    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                        continue
                    attachment_id_candidates = _normalize_identifier_candidates(item.get("id"))
                    stable_id = attachment_id_candidates[0] if attachment_id_candidates else item["name"]
                    normalized_message_id = str(uuid5(
                        NAMESPACE_URL,
                        f"{user_id}:{conversation_id}:{source_message_id or f'attachment:{stable_id}'}",
                    ))
                    found.append({
                        "id": item.get("id"), "stable_id": stable_id, "name": item["name"],
                        "mime_type": item.get("mime_type") if isinstance(item.get("mime_type"), str) else None,
                        "size": item.get("size") if isinstance(item.get("size"), int) and item["size"] >= 0 else None,
                        "conversation_id": conversation_id, "message_id": normalized_message_id,
                        "source_message_id": source_message_id,
                    })
    return found


def _library_matches(raw: dict, library: list) -> list[dict]:
    raw_identifiers = set(_normalize_identifier_candidates(raw.get("id")))
    exact = [item for item in library if isinstance(item, dict)
             and raw_identifiers
             and raw_identifiers & (
                 set(_normalize_identifier_candidates(item.get("id")))
                 | set(_normalize_identifier_candidates(item.get("file_id")))
             )
             and _provenance_matches(raw, item)]
    if exact:
        return exact
    return [item for item in library if isinstance(item, dict)
            and isinstance(item.get("file_name"), str)
            and item["file_name"].casefold() == raw["name"].casefold()
            and _provenance_matches(raw, item)]


def _provenance_matches(raw: dict, item: dict) -> bool:
    conversation_values = set(
        _normalize_identifier_candidates(item.get("initiating_conversation_id"))
        + _normalize_identifier_candidates(item.get("origination_thread_id"))
    )
    message_values = set(_normalize_identifier_candidates(item.get("origination_message_id")))
    stated = bool(conversation_values or message_values)
    return not stated or raw["conversation_id"] in conversation_values or raw.get("source_message_id") in message_values


def _candidate_paths(raw: dict, library: dict | None, names: dict, logical: object, entries: dict) -> list[str]:
    identifiers = set(_normalize_identifier_candidates(raw.get("id")))
    if library:
        identifiers.update(_normalize_identifier_candidates(library.get("id")))
        identifiers.update(_normalize_identifier_candidates(library.get("file_id")))
    asset_keys = {key for identifier in identifiers for key in (identifier, f"{identifier}.dat") if key in names or key in logical}
    if not asset_keys:
        matching_names = [key for key, value in names.items() if isinstance(value, str) and value.casefold() == raw["name"].casefold()]
        if len(matching_names) == 1:
            asset_keys.add(matching_names[0])
        elif len(matching_names) > 1:
            return [f"<ambiguous-{index}>" for index in range(len(matching_names))]
    paths: set[str] = set()
    for key in asset_keys:
        value = logical.get(key) if isinstance(logical, dict) else None
        listed = value.get("files", []) if isinstance(value, dict) else []
        candidates = listed if listed else [key]
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            safe = PurePosixPath(candidate.replace("\\", "/"))
            if not safe.is_absolute() and ".." not in safe.parts:
                paths.add(safe.as_posix())
    return sorted(paths)


def _library_id(value: dict | None) -> str | None:
    if not value:
        return None
    return next((candidate for key in ("file_id", "id")
                 for candidate in _normalize_identifier_candidates(value.get(key))), None)


def _normalize_identifier_candidates(value: object) -> tuple[str, ...]:
    """Extract only explicit scalar identifiers from supported schema shapes."""
    candidates: list[str] = []
    if isinstance(value, str):
        normalized = value.strip()
        if normalized and len(normalized) <= 512:
            candidates.append(normalized)
    elif isinstance(value, dict):
        for key, child in value.items():
            if key in _SUPPORTED_IDENTIFIER_KEYS:
                candidates.extend(_normalize_identifier_candidates(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            candidates.extend(_normalize_identifier_candidates(child))
    return tuple(dict.fromkeys(candidates))


def _is_pdf(filename: str, mime_type: str | None) -> bool:
    return filename.lower().endswith(".pdf") or (mime_type or "").lower() == "application/pdf"
