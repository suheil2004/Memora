import { describe, expect, it } from "vitest";

import { isRetrieveRequest } from "../src/background-listener";
import { normalizeBackendUrl } from "../src/settings";

describe("extension security boundaries", () => {
  it("accepts only the exact retrieval message schema and bounded query", () => {
    expect(isRetrieveRequest({ type: "MEMORA_RETRIEVE_CONTEXT", query: "hello" })).toBe(true);
    expect(isRetrieveRequest({ type: "UNKNOWN", query: "hello" })).toBe(false);
    expect(isRetrieveRequest({ type: "MEMORA_RETRIEVE_CONTEXT" })).toBe(false);
    expect(isRetrieveRequest({ type: "MEMORA_RETRIEVE_CONTEXT", query: 7 })).toBe(false);
    expect(isRetrieveRequest({ type: "MEMORA_RETRIEVE_CONTEXT", query: " " })).toBe(false);
    expect(isRetrieveRequest({ type: "MEMORA_RETRIEVE_CONTEXT", query: "x".repeat(2001) })).toBe(false);
    expect(isRetrieveRequest({ type: "MEMORA_RETRIEVE_CONTEXT", query: "hello", user_id: "user-b" })).toBe(false);
    expect(isRetrieveRequest({ type: "MEMORA_RETRIEVE_CONTEXT", query: "hello", url: "http://example.invalid" })).toBe(false);
  });

  it("allows only the fixed local Memora backend origins", () => {
    expect(normalizeBackendUrl("http://127.0.0.1:8765")).toBe("http://127.0.0.1:8765");
    expect(normalizeBackendUrl("http://localhost:8765/")).toBe("http://localhost:8765");
    for (const value of [
      "file:///tmp/memora", "javascript:alert(1)", "data:text/plain,test",
      "https://127.0.0.1:8765", "http://127.0.0.1:8000",
      "http://example.invalid:8765", "https://example.invalid",
      "http://user:password@localhost:8765", "http://localhost:8765/unexpected",
    ]) {
      expect(() => normalizeBackendUrl(value)).toThrow();
    }
  });
});
