import { describe, expect, it, vi } from "vitest";

import { MemoraApiClient } from "../src/api/memora-client";
import type { BackgroundRequest } from "../src/api/types";
import { handleBackgroundRequest, type BackgroundDependencies } from "../src/background-handler";
import { registerBackgroundListener, type BackgroundRuntime } from "../src/background-listener";
import { requestMemoraContext, type RuntimeMessenger } from "../src/messaging";
import { MemoraPanel } from "../src/panel";

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
  memories: [{ thread_id: "thread-1", title: "Drone Detection Project", subject: "user",
    summary: "A Raspberry Pi streams the feed and a CUDA laptop runs inference.",
    key_details: ["Raspberry Pi 4 streams the camera feed.", "Windows laptop with CUDA performs inference."],
    sources: [{ type: "conversation", conversation_id: "conv-drone", conversation_title: "Drone Detection Project" }], used_fallback: false }],
};

const exactBackendResponse = {
  query: "How was the camera feed being processed in my drone detection setup?",
  context: `[Memora Context]
Source: Drone Detection Project

User previously discussed:

* User: A Raspberry Pi 4 streams the camera feed.
* User: A Windows laptop with CUDA performs inference.
[/Memora Context]`,
  results: [{
    user_id: "demo-user",
    conversation_id: "conv_drone_001",
    conversation_title: "Drone Detection Project",
    chunk_id: "chunk-drone-1",
    score: 0.6348452862421988,
    source_message_ids: ["message-drone-1"],
  }],
  memories: [{ thread_id: "thread-drone", title: "Drone Detection Project", subject: "user",
    summary: "The Pi streams camera video to a Windows CUDA laptop for inference.",
    key_details: ["A Raspberry Pi 4 streams the camera feed.", "A Windows laptop with CUDA performs inference."],
    sources: [{ type: "conversation", conversation_id: "conv_drone_001", conversation_title: "Drone Detection Project" }], used_fallback: false }],
};

function dependencies(fetchImpl: typeof fetch): BackgroundDependencies {
  return {
    loadSettings: async () => ({
      backendUrl: "http://127.0.0.1:8765",
      localToken: "synthetic-memora-token-00000000000",
      topK: 5,
    }),
    hasHostPermission: async () => true,
    createClient: (url, token) => new MemoraApiClient(url, token, fetchImpl),
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
      query: "Where is inference running?",
      top_k: 5,
    });
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer synthetic-memora-token-00000000000");
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

  it("carries the exact successful API response through messaging and renders it", async () => {
    document.body.innerHTML = "";
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(exactBackendResponse), { status: 200 }),
    );
    const runtime: RuntimeMessenger = {
      sendMessage: (message: BackgroundRequest) =>
        handleBackgroundRequest(message, dependencies(fetchMock)),
    };
    const response = await requestMemoraContext(exactBackendResponse.query, runtime);
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults(response);

    const root = document.querySelector<HTMLElement>("#memora-extension-root")!.shadowRoot!;
    const status = root.querySelector<HTMLElement>("#memora-status")!;
    expect(response).toEqual(exactBackendResponse);
    expect(status.dataset.state).toBe("results");
    expect(root.textContent).toContain("Drone Detection Project");
    expect(root.textContent).toContain("A Raspberry Pi 4 streams the camera feed.");
    expect(root.textContent).toContain("A Windows laptop with CUDA performs inference.");
    expect(root.textContent).not.toContain("No relevant memory found");
    expect(root.textContent).not.toContain("Memory retrieval failed");
    expect(root.textContent).toContain("Use This Context");
  });
});
