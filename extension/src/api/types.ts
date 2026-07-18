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
}

export interface RetrieveRequest {
  user_id: string;
  query: string;
  top_k: number;
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
