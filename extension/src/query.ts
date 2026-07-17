export function requireDraftQuery(query: string | null): string {
  const normalized = query?.trim() ?? "";
  if (!normalized) {
    throw new Error("Type a message in ChatGPT before retrieving memory.");
  }
  return normalized;
}
