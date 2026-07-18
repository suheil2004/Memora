import { beforeEach, describe, expect, it } from "vitest";

import { renderImportError, renderImportSummary } from "../src/import-ui";

describe("ChatGPT import status rendering", () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="status"></div>';
  });

  it("renders aggregate counts and sanitized errors", () => {
    const target = document.querySelector<HTMLElement>("#status")!;
    renderImportSummary(target, {
      conversations_found: 10,
      conversations_imported: 8,
      conversations_skipped: 2,
      messages_imported: 42,
      chunks_indexed: 12,
      embedding_provider: "local",
      embedding_model: "feature-hash-v1-1024",
      duration_seconds: 1.25,
      errors: ["conversation 9: unsupported shape"],
    });
    expect(target.textContent).toContain("Imported 8 of 10 conversations");
    expect(target.textContent).toContain("42 messages, 12 chunks, 2 skipped (1.3s)");
    expect(target.textContent).toContain("unsupported shape");
  });

  it("replaces previous output with a useful import error", () => {
    const target = document.querySelector<HTMLElement>("#status")!;
    target.textContent = "old status";
    renderImportError(target, "The export could not be imported.");
    expect(target.textContent).toBe("The export could not be imported.");
  });
});
