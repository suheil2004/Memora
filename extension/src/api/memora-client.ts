import type { BulkImportSummary, ContextResponse, DocumentImportSummary, ExtensionErrorCode, MemoryClearResponse, MemoryStatistics, RetrieveRequest } from "./types";

export const RETRIEVAL_TIMEOUT_MS = 60_000;
export const READINESS_TIMEOUT_MS = 10_000;

export class MemoraApiError extends Error {
  constructor(
    readonly code: ExtensionErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "MemoraApiError";
  }
}

export class MemoraApiClient {
  constructor(
    private readonly baseUrl: string,
    private readonly localToken: string,
    private readonly fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
    private readonly retrievalTimeoutMs: number = RETRIEVAL_TIMEOUT_MS,
    private readonly readinessTimeoutMs: number = READINESS_TIMEOUT_MS,
  ) {}

  async retrieve(request: RetrieveRequest): Promise<ContextResponse> {
    let response: Response;
    try {
      response = await this.fetchWithTimeout(`${this.baseUrl.replace(/\/$/, "")}/api/v1/context/retrieve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${this.localToken}`,
        },
        body: JSON.stringify(request),
      }, this.retrievalTimeoutMs);
    } catch (error) {
      if (error instanceof MemoraApiError) throw error;
      throw new MemoraApiError(
        "BACKEND_UNREACHABLE",
        "Memora could not reach the local backend. Confirm it is running and test the connection in Memora settings.",
      );
    }
    if (!response.ok) {
      throw await responseError(response, `Memora request failed (${response.status}).`);
    }
    const value: unknown = await response.json().catch(() => null);
    if (!isContextResponse(value)) {
      throw new MemoraApiError("INVALID_RESPONSE", "Memora returned a malformed response.");
    }
    return value;
  }

  async health(): Promise<void> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl.replace(/\/$/, "")}/health`);
    } catch {
      throw new MemoraApiError(
        "CORS_OR_PERMISSION_ERROR",
        "Chrome could not access the local backend. Allow local network access if prompted.",
      );
    }
    if (!response.ok) {
      throw new MemoraApiError("HTTP_ERROR", `Memora health check failed (${response.status}).`);
    }
    const value: unknown = await response.json().catch(() => null);
    if (!isRecord(value) || value.status !== "ok" || value.service !== "memora") {
      throw new MemoraApiError("INVALID_RESPONSE", "The configured URL did not return a valid Memora health response.");
    }
  }

  async importChatGPTHistory(files: readonly File[]): Promise<BulkImportSummary> {
    if (files.length === 0) {
      throw new MemoraApiError("INVALID_RESPONSE", "Select at least one ChatGPT export file.");
    }
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl.replace(/\/$/, "")}/api/v1/import/chatgpt`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${this.localToken}` },
        body: form,
      });
    } catch {
      throw new MemoraApiError(
        "BACKEND_UNREACHABLE",
        "Memora could not reach the local backend during import.",
      );
    }
    if (!response.ok) {
      const message = await safeErrorMessage(response);
      throw new MemoraApiError("HTTP_ERROR", message || `ChatGPT import failed (${response.status}).`);
    }
    const value: unknown = await response.json().catch(() => null);
    if (!isBulkImportSummary(value)) {
      throw new MemoraApiError("INVALID_RESPONSE", "Memora returned a malformed import summary.");
    }
    return value;
  }

  async importDocuments(files: readonly File[]): Promise<DocumentImportSummary> {
    if (files.length === 0) throw new MemoraApiError("INVALID_RESPONSE", "Select at least one PDF.");
    const form = new FormData();
    files.forEach((file) => form.append("files", file, file.name));
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl.replace(/\/$/, "")}/api/v1/import/documents`, {
        method: "POST", headers: { "Authorization": `Bearer ${this.localToken}` }, body: form,
      });
    } catch {
      throw new MemoraApiError("BACKEND_UNREACHABLE", "Memora could not reach the local backend during document import.");
    }
    if (!response.ok) throw new MemoraApiError("HTTP_ERROR", await safeErrorMessage(response) || `Document import failed (${response.status}).`);
    const value: unknown = await response.json().catch(() => null);
    if (!isDocumentImportSummary(value)) throw new MemoraApiError("INVALID_RESPONSE", "Memora returned a malformed document summary.");
    return value;
  }

  async memoryStatistics(): Promise<MemoryStatistics> {
    const response = await this.authenticatedRequest(
      "/api/v1/memory/stats", "GET", this.readinessTimeoutMs,
    );
    const value: unknown = await response.json().catch(() => null);
    if (!isMemoryStatistics(value)) {
      throw new MemoraApiError("INVALID_RESPONSE", "Memora returned malformed memory statistics.");
    }
    return value;
  }

  async clearMemory(): Promise<MemoryClearResponse> {
    const response = await this.authenticatedRequest("/api/v1/memory", "DELETE");
    const value: unknown = await response.json().catch(() => null);
    if (!isRecord(value) || value.cleared !== true ||
        typeof value.rows_deleted !== "number" || !Number.isInteger(value.rows_deleted) ||
        value.rows_deleted < 0) {
      throw new MemoraApiError("INVALID_RESPONSE", "Memora returned a malformed deletion response.");
    }
    return value as unknown as MemoryClearResponse;
  }

  private async authenticatedRequest(
    path: string,
    method: "GET" | "DELETE",
    timeoutMs?: number,
  ): Promise<Response> {
    let response: Response;
    try {
      const url = `${this.baseUrl.replace(/\/$/, "")}${path}`;
      response = timeoutMs === undefined
        ? await this.fetchImpl(url, {
          method, headers: { "Authorization": `Bearer ${this.localToken}` },
        })
        : await this.fetchWithTimeout(url, {
        method, headers: { "Authorization": `Bearer ${this.localToken}` },
      }, timeoutMs);
    } catch (error) {
      if (error instanceof MemoraApiError) throw error;
      throw new MemoraApiError("BACKEND_UNREACHABLE", "Memora could not reach the local backend.");
    }
    if (!response.ok) {
      throw await responseError(response, `Memora request failed (${response.status}).`);
    }
    return response;
  }

  private async fetchWithTimeout(
    url: string,
    init: RequestInit,
    timeoutMs: number,
  ): Promise<Response> {
    const controller = new AbortController();
    const timer = globalThis.setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await this.fetchImpl(url, { ...init, signal: controller.signal });
    } catch (error) {
      if (controller.signal.aborted) {
        throw new MemoraApiError(
          "REQUEST_TIMEOUT",
          "Memora did not respond within the allowed time.",
        );
      }
      throw error;
    } finally {
      globalThis.clearTimeout(timer);
    }
  }
}

export function isContextResponse(value: unknown): value is ContextResponse {
  if (!isRecord(value) || typeof value.query !== "string" || typeof value.context !== "string") return false;
  if (!Array.isArray(value.results)) return false;
  const validResults = value.results.every((result) =>
    isRecord(result) &&
    typeof result.user_id === "string" &&
    typeof result.conversation_id === "string" &&
    (typeof result.conversation_title === "string" || result.conversation_title === null) &&
    typeof result.chunk_id === "string" &&
    typeof result.score === "number" && Number.isFinite(result.score) &&
    Array.isArray(result.source_message_ids) &&
    result.source_message_ids.every((id) => typeof id === "string"),
  );
  if (!validResults || !Array.isArray(value.memories)) return false;
  return value.memories.every((memory) =>
    isRecord(memory) && typeof memory.thread_id === "string" &&
    typeof memory.title === "string" && typeof memory.subject === "string" &&
    typeof memory.summary === "string" && Array.isArray(memory.key_details) &&
    memory.key_details.every((detail) => typeof detail === "string") &&
    Array.isArray(memory.sources) && memory.sources.every(isMemorySource) &&
    typeof memory.used_fallback === "boolean" &&
    (memory.latest_timestamp === undefined || memory.latest_timestamp === null ||
      (typeof memory.latest_timestamp === "string" && Number.isFinite(Date.parse(memory.latest_timestamp))))
  );
}

export function isBulkImportSummary(value: unknown): value is BulkImportSummary {
  if (!isRecord(value)) return false;
  const countKeys = [
    "conversations_found", "conversations_imported", "conversations_skipped",
    "messages_imported", "chunks_indexed", "duration_seconds", "documents_found",
    "documents_imported", "documents_skipped", "document_chunks_indexed",
    "document_references_missing",
    "attachments_found", "attachments_imported", "pdf_references_found",
    "pdf_binaries_resolved", "pdf_binaries_indexed", "attachments_metadata_only",
    "attachments_ambiguous", "attachments_missing", "attachments_unsupported",
  ] as const;
  return countKeys.every((key) => typeof value[key] === "number" && Number.isFinite(value[key])) &&
    typeof value.embedding_provider === "string" &&
    typeof value.embedding_model === "string" &&
    Array.isArray(value.errors) && value.errors.every((error) => typeof error === "string");
}

function isDocumentImportSummary(value: unknown): value is DocumentImportSummary {
  if (!isRecord(value)) return false;
  return ["documents_found", "documents_imported", "documents_skipped", "document_chunks_indexed", "duration_seconds"]
    .every((key) => typeof value[key] === "number" && Number.isFinite(value[key])) &&
    typeof value.embedding_provider === "string" && typeof value.embedding_model === "string" &&
    Array.isArray(value.errors) && value.errors.every((error) => typeof error === "string");
}

function isMemoryStatistics(value: unknown): value is MemoryStatistics {
  if (!isRecord(value)) return false;
  return ["conversations", "conversation_chunks", "attachments", "documents", "document_chunks"]
    .every((key) => typeof value[key] === "number" && Number.isInteger(value[key]) && value[key] >= 0);
}

function isMemorySource(value: unknown): boolean {
  if (!isRecord(value)) return false;
  if (value.type === "conversation") {
    return typeof value.conversation_id === "string" && typeof value.conversation_title === "string";
  }
  if (value.type === "attachment") {
    return typeof value.attachment_id === "string" && typeof value.filename === "string" &&
      (typeof value.mime_type === "string" || value.mime_type === null) &&
      typeof value.conversation_id === "string" && typeof value.message_id === "string" &&
      ["resolved", "metadata_only", "ambiguous", "missing", "unsupported"].includes(
        String(value.binary_resolution_status),
      );
  }
  return value.type === "document" && typeof value.document_id === "string" &&
    typeof value.filename === "string" && typeof value.page_start === "number" &&
    typeof value.page_end === "number" &&
    (typeof value.parent_conversation_id === "string" || value.parent_conversation_id === null);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function safeErrorMessage(response: Response): Promise<string | null> {
  const body: unknown = await response.json().catch(() => null);
  return isRecord(body) && typeof body.detail === "string" ? body.detail : null;
}

async function responseError(response: Response, fallback: string): Promise<MemoraApiError> {
  if (response.status === 401) {
    return new MemoraApiError(
      "AUTHENTICATION_FAILED",
      "The extension token does not match the local Memora service.",
    );
  }
  if (response.status === 409 || response.status === 503) {
    return new MemoraApiError(
      "CONFIGURATION_UNAVAILABLE",
      "The local Memora service is not ready to use its configured memory provider.",
    );
  }
  return new MemoraApiError("HTTP_ERROR", await safeErrorMessage(response) || fallback);
}
