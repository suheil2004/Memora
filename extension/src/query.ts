import { MAX_QUERY_LENGTH } from "./security";

export function requireDraftQuery(query: string | null): string {
  const normalized = query?.trim() ?? "";
  if (!normalized) {
    throw new Error("Type a message in ChatGPT before retrieving memory.");
  }
  if (normalized.length > MAX_QUERY_LENGTH) {
    throw new Error(`Keep the ChatGPT draft under ${MAX_QUERY_LENGTH.toLocaleString()} characters before retrieving memory.`);
  }
  return normalized;
}
