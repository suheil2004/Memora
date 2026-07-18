import { afterEach, describe, expect, it, vi } from "vitest";

import { MemoraApiClient, MemoraApiError, isContextResponse } from "../src/api/memora-client";

const validResponse = {
  query: "Where is inference running?",
  context: "[Memora Context]...",
  results: [{
    user_id: "demo-user",
    conversation_id: "conv-1",
    conversation_title: "Drone Detection Project",
    chunk_id: "chunk-1",
    score: 0.82,
    source_message_ids: ["message-1"],
  }],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MemoraApiClient", () => {
  it("sends the retrieval request and parses a valid response", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(validResponse), { status: 200 }),
    );
    const client = new MemoraApiClient("http://127.0.0.1:8765/", fetchMock);

    const result = await client.retrieve({ user_id: "demo-user", query: "query", top_k: 5 });

    expect(result).toEqual(validResponse);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8765/api/v1/context/retrieve");
  });

  it("rejects malformed responses", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ context: 42 }), { status: 200 }),
    );
    await expect(
      new MemoraApiClient("http://localhost:8765", fetchMock).retrieve({
        user_id: "u1", query: "query", top_k: 5,
      }),
    ).rejects.toThrow("malformed response");
  });

  it("reports an unavailable backend without leaking fetch details", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(new Error("socket secret"));
    await expect(
      new MemoraApiClient("http://localhost:8765", fetchMock).retrieve({
        user_id: "u1", query: "query", top_k: 5,
      }),
    ).rejects.toBeInstanceOf(MemoraApiError);
  });

  it("binds the native fetch receiver before invoking it", async () => {
    const receiverSensitiveFetch = vi.fn(function (this: unknown) {
      if (this !== globalThis) throw new TypeError("Illegal invocation");
      return Promise.resolve(new Response(JSON.stringify(validResponse), { status: 200 }));
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", receiverSensitiveFetch);

    await expect(
      new MemoraApiClient("http://127.0.0.1:8765").retrieve({
        user_id: "demo-user", query: "query", top_k: 5,
      }),
    ).resolves.toEqual(validResponse);
    expect(receiverSensitiveFetch).toHaveBeenCalledOnce();
  });

  it("classifies HTTP and malformed response failures", async () => {
    const httpFetch = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ detail: "request rejected" }), { status: 503 }),
    );
    const invalidFetch = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ query: "q", context: "c", results: "bad" }), { status: 200 }),
    );
    await expect(
      new MemoraApiClient("http://localhost:8765", httpFetch).retrieve({ user_id: "u", query: "q", top_k: 1 }),
    ).rejects.toMatchObject({ code: "HTTP_ERROR" });
    await expect(
      new MemoraApiClient("http://localhost:8765", invalidFetch).retrieve({ user_id: "u", query: "q", top_k: 1 }),
    ).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});

describe("isContextResponse", () => {
  it("validates nested provenance", () => {
    expect(isContextResponse(validResponse)).toBe(true);
    expect(isContextResponse({ ...validResponse, results: [{ score: "high" }] })).toBe(false);
  });
});
