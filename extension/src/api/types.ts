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

export type BackgroundRequest = { type: "MEMORA_RETRIEVE"; query: string };
export type BackgroundResponse =
  | { ok: true; data: ContextResponse }
  | { ok: false; error: string };
