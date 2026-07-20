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
      documents_found: 0, documents_imported: 0, documents_skipped: 0,
      document_chunks_indexed: 0, document_references_missing: 0,
      attachments_found: 0, attachments_imported: 0, pdf_references_found: 0,
      pdf_binaries_resolved: 0, pdf_binaries_indexed: 0, attachments_metadata_only: 0,
      attachments_ambiguous: 0, attachments_missing: 0, attachments_unsupported: 0,
    });
    expect(target.textContent).toContain("Import completed with skips");
    expect(target.textContent).toContain("10 conversations found · 8 imported · 2 skipped");
    expect(target.textContent).toContain("12 memory chunks indexed in 1.3s");
    expect(target.textContent).toContain("unsupported shape");
    expect(target.className).toBe("partial");
  });

  it("replaces previous output with a useful import error", () => {
    const target = document.querySelector<HTMLElement>("#status")!;
    target.textContent = "old status";
    renderImportError(target, "The export could not be imported.");
    expect(target.textContent).toBe("The export could not be imported.");
    expect(target.className).toBe("error");
  });

  it("reports conditionally discovered PDF assets without exposing filenames", () => {
    const target = document.querySelector<HTMLElement>("#status")!;
    renderImportSummary(target, {
      conversations_found: 2,
      conversations_imported: 2,
      conversations_skipped: 0,
      messages_imported: 8,
      chunks_indexed: 3,
      embedding_provider: "local",
      embedding_model: "feature-hash-v1-1024",
      duration_seconds: 0.5,
      errors: [],
      documents_found: 2,
      documents_imported: 1,
      documents_skipped: 1,
      document_chunks_indexed: 2,
      document_references_missing: 1,
      attachments_found: 2, attachments_imported: 2, pdf_references_found: 2,
      pdf_binaries_resolved: 1, pdf_binaries_indexed: 1, attachments_metadata_only: 1,
      attachments_ambiguous: 0, attachments_missing: 0, attachments_unsupported: 0,
    });

    expect(target.textContent).toContain(
      "2 linked PDFs found · 1 imported · 1 skipped · 1 references missing",
    );
    expect(target.textContent).toContain("Attachments discovered: 2");
    expect(target.textContent).toContain("PDFs automatically indexed: 1");
  });
});
