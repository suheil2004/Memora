import { describe, expect, it } from "vitest";

import { requireDraftQuery } from "../src/query";

describe("requireDraftQuery", () => {
  it("rejects empty drafts", () => {
    expect(() => requireDraftQuery(null)).toThrow("Type a message");
    expect(() => requireDraftQuery("   ")).toThrow("Type a message");
  });

  it("returns a trimmed non-empty draft", () => {
    expect(requireDraftQuery("  hello  ")).toBe("hello");
  });
});
