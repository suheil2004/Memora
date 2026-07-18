import { describe, expect, it, vi } from "vitest";

import { MemoraApiClient } from "../src/api/memora-client";
import type { BackgroundRequest } from "../src/api/types";
import { handleBackgroundRequest, type BackgroundDependencies } from "../src/background-handler";
import { registerBackgroundListener, type BackgroundRuntime } from "../src/background-listener";
import { requestMemoraContext, type RuntimeMessenger } from "../src/messaging";

const apiResponse = {
  query: "Where is inference running?",
  context: "[Memora Context] Drone Detection Project",
  results: [{
    user_id: "demo-user",
    conversation_id: "conv-drone",
    conversation_title: "Drone Detection Project",
    chunk_id: "chunk-1",
    score: 0.82,
    source_message_ids: ["message-1"],
  }],
};

function dependencies(fetchImpl: typeof fetch): BackgroundDependencies {
  return {
    loadSettings: async () => ({
      backendUrl: "http://127.0.0.1:8765",
      userId: "demo-user",
      topK: 5,
    }),
    hasHostPermission: async () => true,
    createClient: (url) => new MemoraApiClient(url, fetchImpl),
  };
}

describe("content-to-background retrieval messaging", () => {
  it("passes a typed request through the background handler to the API client", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(apiResponse), { status: 200 }),
    );
    const runtime: RuntimeMessenger = {
      sendMessage: (message: BackgroundRequest) => handleBackgroundRequest(message, dependencies(fetchMock)),
    };

    const response = await requestMemoraContext("Where is inference running?", runtime);

    expect(response).toEqual(apiResponse);
    expect(fetchMock).toHaveBeenCalledOnce();
    const init = fetchMock.mock.calls[0]?.[1];
    expect(JSON.parse(String(init?.body))).toEqual({
      user_id: "demo-user",
      query: "Where is inference running?",
      top_k: 5,
    });
  });

  it("propagates an unreachable-backend error through the service worker response", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("Failed to fetch"));
    const message: BackgroundRequest = {
      type: "MEMORA_RETRIEVE_CONTEXT",
      query: "Where is inference running?",
    };
    const backgroundResponse = await handleBackgroundRequest(message, dependencies(fetchMock));
    expect(backgroundResponse).toMatchObject({
      ok: false,
      error: { code: "BACKEND_UNREACHABLE" },
    });

    const runtime: RuntimeMessenger = { sendMessage: async () => backgroundResponse };
    await expect(requestMemoraContext(message.query, runtime)).rejects.toThrow(
      "could not reach the local backend",
    );
  });

  it("reports missing host permission without attempting a fetch", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    const deps = dependencies(fetchMock);
    deps.hasHostPermission = async () => false;
    const response = await handleBackgroundRequest(
      { type: "MEMORA_RETRIEVE_CONTEXT", query: "query" },
      deps,
    );
    expect(response).toMatchObject({
      ok: false,
      error: { code: "CORS_OR_PERMISSION_ERROR" },
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the callback response channel open until the async handler completes", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(apiResponse), { status: 200 }),
    );
    let listener: Parameters<BackgroundRuntime["onMessage"]["addListener"]>[0] | undefined;
    const runtime: BackgroundRuntime = {
      onMessage: {
        addListener: (callback) => { listener = callback; },
      },
    };
    registerBackgroundListener(runtime, dependencies(fetchMock));
    expect(listener).toBeDefined();

    const response = new Promise((resolve) => {
      const keepsChannelOpen = listener!(
        { type: "MEMORA_RETRIEVE_CONTEXT", query: "Where is inference running?" },
        {},
        resolve,
      );
      expect(keepsChannelOpen).toBe(true);
    });

    await expect(response).resolves.toMatchObject({ ok: true, data: apiResponse });
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
