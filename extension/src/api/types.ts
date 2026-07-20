export interface RetrievalResult {
  user_id: string;
  conversation_id: string;
  conversation_title: string | null;
  chunk_id: string;
  score: number;
  source_message_ids: string[];
}

export interface ContextResponse {
  query: string;
  context: string;
  results: RetrievalResult[];
  memories: MemoryBrief[];
}

export interface ConversationMemorySource {
  type: "conversation";
  conversation_id: string;
  conversation_title: string;
}
export interface DocumentMemorySource {
  type: "document";
  document_id: string;
  filename: string;
  page_start: number;
  page_end: number;
  parent_conversation_id: string | null;
}
export interface AttachmentMemorySource {
  type: "attachment";
  attachment_id: string;
  filename: string;
  mime_type: string | null;
  conversation_id: string;
  message_id: string;
  binary_resolution_status: "resolved" | "metadata_only" | "ambiguous" | "missing" | "unsupported";
}
export type MemorySource = ConversationMemorySource | DocumentMemorySource | AttachmentMemorySource;

export interface MemoryBrief {
  thread_id: string;
  title: string;
  subject: string;
  summary: string;
  key_details: string[];
  sources: MemorySource[];
  used_fallback: boolean;
  latest_timestamp?: string | null;
}

export interface RetrieveRequest {
  query: string;
  top_k: number;
}

export interface BulkImportSummary {
  conversations_found: number;
  conversations_imported: number;
  conversations_skipped: number;
  messages_imported: number;
  chunks_indexed: number;
  embedding_provider: string;
  embedding_model: string;
  duration_seconds: number;
  errors: string[];
  documents_found: number;
  documents_imported: number;
  documents_skipped: number;
  document_chunks_indexed: number;
  document_references_missing: number;
  attachments_found: number;
  attachments_imported: number;
  pdf_references_found: number;
  pdf_binaries_resolved: number;
  pdf_binaries_indexed: number;
  attachments_metadata_only: number;
  attachments_ambiguous: number;
  attachments_missing: number;
  attachments_unsupported: number;
}

export interface DocumentImportSummary {
  documents_found: number;
  documents_imported: number;
  documents_skipped: number;
  document_chunks_indexed: number;
  embedding_provider: string;
  embedding_model: string;
  duration_seconds: number;
  errors: string[];
}

export type BackgroundRequest = { type: "MEMORA_RETRIEVE_CONTEXT"; query: string };
export type ExtensionErrorCode =
  | "BACKEND_UNREACHABLE"
  | "CORS_OR_PERMISSION_ERROR"
  | "HTTP_ERROR"
  | "INVALID_RESPONSE"
  | "EXTENSION_MESSAGING_ERROR"
  | "INTERNAL_ERROR";
export type BackgroundResponse =
  | { ok: true; data: ContextResponse }
  | { ok: false; error: { code: ExtensionErrorCode; message: string } };
