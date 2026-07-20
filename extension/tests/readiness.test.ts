import { describe, expect, it, vi } from "vitest";

import { MemoraApiError } from "../src/api/memora-client";
import { checkAuthenticatedReadiness } from "../src/readiness";

const empty = {
  conversations: 0, conversation_chunks: 0, attachments: 0,
  documents: 0, document_chunks: 0,
};

describe("authenticated readiness", () => {
  it("reports Ready for an authenticated populated database", async () => {
    const memoryStatistics = vi.fn(async () => ({ ...empty, conversations: 2, conversation_chunks: 8 }));
    await expect(checkAuthenticatedReadiness({ memoryStatistics })).resolves.toMatchObject({
      state: "ready", label: "Ready",
    });
    expect(memoryStatistics).toHaveBeenCalledOnce();
  });

  it("reports No memory imported yet for an authenticated empty database", async () => {
    await expect(checkAuthenticatedReadiness({ memoryStatistics: async () => empty }))
      .resolves.toMatchObject({
        state: "empty",
        label: "No memory imported yet",
        message: "Connected — no memory imported yet. Import your ChatGPT history to begin.",
      });
  });

  it("distinguishes offline, authentication, and configuration failures", async () => {
    const result = async (code: "BACKEND_UNREACHABLE" | "AUTHENTICATION_FAILED" | "CONFIGURATION_UNAVAILABLE") =>
      checkAuthenticatedReadiness({
        memoryStatistics: async () => { throw new MemoraApiError(code, "private detail"); },
      });
    await expect(result("BACKEND_UNREACHABLE")).resolves.toMatchObject({ state: "offline" });
    await expect(result("AUTHENTICATION_FAILED")).resolves.toMatchObject({
      state: "authentication", label: "Authentication failed",
    });
    await expect(result("CONFIGURATION_UNAVAILABLE")).resolves.toMatchObject({
      state: "unavailable", label: "Configuration unavailable",
    });
  });

  it("uses only memory statistics and never a provider-backed retrieval method", async () => {
    const memoryStatistics = vi.fn(async () => empty);
    const retrieve = vi.fn();
    await checkAuthenticatedReadiness({ memoryStatistics });
    expect(memoryStatistics).toHaveBeenCalledOnce();
    expect(retrieve).not.toHaveBeenCalled();
  });
});
