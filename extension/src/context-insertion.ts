import type { ChatSiteAdapter } from "./adapters/chat-site-adapter";
import type { ContextResponse } from "./api/types";

export interface RetrievedContextSnapshot {
  originalQuery: string;
  prompt: string;
  points: string[];
}

export type InsertionStatus =
  | "inserted"
  | "already_inserted"
  | "draft_changed"
  | "missing_input"
  | "failed";

export function createContextSnapshot(
  response: ContextResponse,
  originalQuery: string,
): RetrievedContextSnapshot | null {
  const points = extractContextPoints(response.context);
  if (response.results.length === 0 || points.length === 0) return null;
  const compactPoints = points.slice(0, 8);
  return {
    originalQuery: originalQuery.trim(),
    points: compactPoints,
    prompt: [
      "Relevant context from my previous conversations:",
      "",
      ...compactPoints.map((point) => `- ${point}`),
      "",
      "My question:",
      originalQuery.trim(),
    ].join("\n"),
  };
}

export function applyContextSnapshot(
  adapter: ChatSiteAdapter,
  snapshot: RetrievedContextSnapshot,
): InsertionStatus {
  if (!adapter.hasDraftInput()) return "missing_input";
  const current = adapter.getCurrentDraftQuery();
  if (current === snapshot.prompt) return "already_inserted";
  if (current !== snapshot.originalQuery) return "draft_changed";
  return adapter.setDraftQuery(snapshot.prompt) ? "inserted" : "failed";
}

export function extractContextPoints(context: string): string[] {
  const ignored = /^(?:\[\/?Memora Context\]|Source:|Relevant previous context:|User previously discussed:)/i;
  const seen = new Set<string>();
  const points: string[] = [];
  for (const rawLine of context.split(/\r?\n/)) {
    let line = rawLine.trim();
    if (!line || ignored.test(line)) continue;
    line = line.replace(/^[-*]\s*/, "").replace(/^(?:User|Assistant):\s*/i, "").trim();
    if (!line || line.endsWith("?") || seen.has(line.toLowerCase())) continue;
    seen.add(line.toLowerCase());
    points.push(line);
  }
  return points;
}
