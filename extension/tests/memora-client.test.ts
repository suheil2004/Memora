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
  memories: [{
    thread_id: "thread-1", title: "Drone Detection Project", subject: "user",
    summary: "A Raspberry Pi streams video while a CUDA laptop runs inference.",
    key_details: ["Raspberry Pi handles streaming", "CUDA laptop handles inference"],
    sources: [{ type: "conversation", conversation_id: "conv-1", conversation_title: "Drone Detection Project" }],
    used_fallback: false,
    latest_timestamp: "2026-07-01T12:00:00Z",
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
    const client = new MemoraApiClient("http://127.0.0.1:8765/", "synthetic-token", fetchMock);

    const result = await client.retrieve({ query: "query", top_k: 5 });

    expect(result).toEqual(validResponse);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8765/api/v1/context/retrieve");
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Authorization")).toBe("Bearer synthetic-token");
  });

  it("rejects malformed responses", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ context: 42 }), { status: 200 }),
    );
    await expect(
      new MemoraApiClient("http://localhost:8765", "synthetic-token", fetchMock).retrieve({
        query: "query", top_k: 5,
      }),
    ).rejects.toThrow("malformed response");
  });

  it("reports an unavailable backend without leaking fetch details", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(new Error("socket secret"));
    await expect(
      new MemoraApiClient("http://localhost:8765", "synthetic-token", fetchMock).retrieve({
        query: "query", top_k: 5,
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
      new MemoraApiClient("http://127.0.0.1:8765", "synthetic-token").retrieve({
        query: "query", top_k: 5,
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
      new MemoraApiClient("http://localhost:8765", "synthetic-token", httpFetch).retrieve({ query: "q", top_k: 1 }),
    ).rejects.toMatchObject({ code: "CONFIGURATION_UNAVAILABLE" });
    await expect(
      new MemoraApiClient("http://localhost:8765", "synthetic-token", invalidFetch).retrieve({ query: "q", top_k: 1 }),
    ).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("uploads selected ChatGPT exports as multipart and validates the summary", async () => {
    const summary = {
      conversations_found: 4,
      conversations_imported: 3,
      conversations_skipped: 1,
      messages_imported: 5,
      chunks_indexed: 3,
      embedding_provider: "local",
      embedding_model: "feature-hash-v1-1024",
      duration_seconds: 0.4,
      errors: ["one synthetic conversation was skipped"],
      documents_found: 0, documents_imported: 0, documents_skipped: 0,
      document_chunks_indexed: 0, document_references_missing: 0,
      attachments_found: 0, attachments_imported: 0, pdf_references_found: 0,
      pdf_binaries_resolved: 0, pdf_binaries_indexed: 0, attachments_metadata_only: 0,
      attachments_ambiguous: 0, attachments_missing: 0, attachments_unsupported: 0,
    };
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(summary), { status: 200 }),
    );
    const file = new File(["[]"], "conversations.json", { type: "application/json" });

    await expect(
      new MemoraApiClient("http://127.0.0.1:8765", "synthetic-token", fetchMock)
        .importChatGPTHistory([file]),
    ).resolves.toEqual(summary);

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://127.0.0.1:8765/api/v1/import/chatgpt");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer synthetic-token");
    expect(init?.body).toBeInstanceOf(FormData);
    const body = init?.body as FormData;
    expect(body.get("user_id")).toBeNull();
    expect((body.get("files") as File).name).toBe("conversations.json");
  });

  it("rejects empty file selections and malformed import summaries", async () => {
    const client = new MemoraApiClient("http://127.0.0.1:8765", "synthetic-token", vi.fn<typeof fetch>());
    await expect(client.importChatGPTHistory([])).rejects.toThrow("Select at least one");

    const invalidFetch = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ conversations_found: "many" }), { status: 200 }),
    );
    await expect(
      new MemoraApiClient("http://127.0.0.1:8765", "synthetic-token", invalidFetch)
        .importChatGPTHistory([new File(["[]"], "conversations.json")]),
    ).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("uploads PDFs to the authenticated document endpoint", async () => {
    const summary = {
      documents_found: 1, documents_imported: 1, documents_skipped: 0,
      document_chunks_indexed: 2, embedding_provider: "local",
      embedding_model: "feature-hash-v1-1024", duration_seconds: 0.2, errors: [],
    };
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(summary), { status: 200 }),
    );
    const client = new MemoraApiClient("http://127.0.0.1:8765", "synthetic-token", fetchMock);
    await expect(client.importDocuments([
      new File(["%PDF-synthetic"], "practice.pdf", { type: "application/pdf" }),
    ])).resolves.toEqual(summary);
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/v1/import/documents");
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Authorization")).toBe("Bearer synthetic-token");
  });

  it("loads aggregate memory statistics and sends one authenticated delete", async () => {
    const memoryStats = {
      conversations: 2, conversation_chunks: 4, attachments: 1,
      documents: 1, document_chunks: 3,
    };
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify(memoryStats), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ cleared: true, rows_deleted: 11 }), { status: 200 }));
    const client = new MemoraApiClient("http://127.0.0.1:8765", "synthetic-token", fetchMock);
    await expect(client.memoryStatistics()).resolves.toEqual(memoryStats);
    await expect(client.clearMemory()).resolves.toEqual({ cleared: true, rows_deleted: 11 });
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("DELETE");
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Authorization"))
      .toBe("Bearer synthetic-token");
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBeUndefined();
  });

  it("classifies authentication failures without exposing backend details", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ detail: "private authentication detail" }), { status: 401 }),
    );
    await expect(
      new MemoraApiClient("http://127.0.0.1:8765", "wrong-token", fetchMock)
        .memoryStatistics(),
    ).rejects.toMatchObject({
      code: "AUTHENTICATION_FAILED",
      message: "The extension token does not match the local Memora service.",
    });
  });

  it("aborts retrieval after the configured timeout", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn<typeof fetch>().mockImplementation((_url, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      })
    );
    const client = new MemoraApiClient(
      "http://127.0.0.1:8765", "synthetic-token", fetchMock, 100,
    );
    const retrieval = client.retrieve({ query: "query", top_k: 1 });
    const assertion = expect(retrieval).rejects.toMatchObject({ code: "REQUEST_TIMEOUT" });
    await vi.advanceTimersByTimeAsync(100);
    await assertion;
    expect((fetchMock.mock.calls[0]?.[1]?.signal as AbortSignal).aborted).toBe(true);
    vi.useRealTimers();
  });
});

describe("isContextResponse", () => {
  it("validates nested provenance", () => {
    expect(isContextResponse(validResponse)).toBe(true);
    expect(isContextResponse({ ...validResponse, results: [{ score: "high" }] })).toBe(false);
    expect(isContextResponse({ ...validResponse, memories: [{ summary: 42 }] })).toBe(false);
    expect(isContextResponse({
      ...validResponse,
      memories: [{ ...validResponse.memories[0], latest_timestamp: "not-a-date" }],
    })).toBe(false);
    expect(isContextResponse({
      ...validResponse,
      memories: [{ ...validResponse.memories[0], latest_timestamp: undefined }],
    })).toBe(true);
  });
});
