import type { BulkImportSummary, ContextResponse, ExtensionErrorCode, RetrieveRequest } from "./types";

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
    private readonly fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {}

  async retrieve(request: RetrieveRequest): Promise<ContextResponse> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl.replace(/\/$/, "")}/api/v1/context/retrieve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
    } catch {
      throw new MemoraApiError(
        "BACKEND_UNREACHABLE",
        "Memora could not reach the local backend. Confirm it is running and test the connection in Memora settings.",
      );
    }
    if (!response.ok) {
      const message = await safeErrorMessage(response);
      throw new MemoraApiError("HTTP_ERROR", message || `Memora request failed (${response.status}).`);
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

  async importChatGPTHistory(files: readonly File[], userId: string): Promise<BulkImportSummary> {
    if (files.length === 0) {
      throw new MemoraApiError("INVALID_RESPONSE", "Select at least one ChatGPT export file.");
    }
    const form = new FormData();
    form.append("user_id", userId);
    for (const file of files) form.append("files", file, file.name);
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl.replace(/\/$/, "")}/api/v1/import/chatgpt`, {
        method: "POST",
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
}

export function isContextResponse(value: unknown): value is ContextResponse {
  if (!isRecord(value) || typeof value.query !== "string" || typeof value.context !== "string") return false;
  if (!Array.isArray(value.results)) return false;
  return value.results.every((result) =>
    isRecord(result) &&
    typeof result.user_id === "string" &&
    typeof result.conversation_id === "string" &&
    (typeof result.conversation_title === "string" || result.conversation_title === null) &&
    typeof result.chunk_id === "string" &&
    typeof result.score === "number" && Number.isFinite(result.score) &&
    Array.isArray(result.source_message_ids) &&
    result.source_message_ids.every((id) => typeof id === "string"),
  );
}

export function isBulkImportSummary(value: unknown): value is BulkImportSummary {
  if (!isRecord(value)) return false;
  const countKeys = [
    "conversations_found", "conversations_imported", "conversations_skipped",
    "messages_imported", "chunks_indexed", "duration_seconds",
  ] as const;
  return countKeys.every((key) => typeof value[key] === "number" && Number.isFinite(value[key])) &&
    typeof value.embedding_provider === "string" &&
    typeof value.embedding_model === "string" &&
    Array.isArray(value.errors) && value.errors.every((error) => typeof error === "string");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function safeErrorMessage(response: Response): Promise<string | null> {
  const body: unknown = await response.json().catch(() => null);
  return isRecord(body) && typeof body.detail === "string" ? body.detail : null;
}
