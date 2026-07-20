import type { BulkImportSummary } from "./api/types";

export function renderImportSummary(target: HTMLElement, summary: BulkImportSummary): void {
  target.replaceChildren();
  const partial = summary.conversations_skipped > 0 || summary.attachments_ambiguous > 0 ||
    summary.attachments_missing > 0 || summary.errors.length > 0;
  target.className = partial ? "partial" : "success";
  const headline = document.createElement("strong");
  headline.textContent = partial ? "Import completed with skips" : "Import complete";
  const details = document.createElement("span");
  details.textContent = `${summary.conversations_found.toLocaleString()} conversations found · ${summary.conversations_imported.toLocaleString()} imported · ${summary.conversations_skipped.toLocaleString()} skipped`;
  const chunks = document.createElement("span");
  chunks.textContent = `${summary.chunks_indexed.toLocaleString()} memory chunks indexed in ${summary.duration_seconds.toFixed(1)}s`;
  target.append(headline, details, chunks);
  if (summary.attachments_found > 0) {
    const attachments = document.createElement("span");
    attachments.textContent = `Attachments discovered: ${summary.attachments_found.toLocaleString()} · PDFs automatically indexed: ${summary.pdf_binaries_indexed.toLocaleString()} · Attachment-only memories: ${summary.attachments_metadata_only.toLocaleString()}`;
    target.append(attachments);
  }
  if (summary.documents_found > 0 || summary.document_references_missing > 0) {
    const documents = document.createElement("span");
    documents.textContent = `${summary.documents_found.toLocaleString()} linked PDFs found · ${summary.documents_imported.toLocaleString()} imported · ${summary.documents_skipped.toLocaleString()} skipped · ${summary.document_references_missing.toLocaleString()} references missing`;
    target.append(documents);
  }
  if (summary.errors.length > 0) {
    const errors = document.createElement("ul");
    for (const message of summary.errors.slice(0, 10)) {
      const item = document.createElement("li");
      item.textContent = message;
      errors.append(item);
    }
    target.append(errors);
  }
}

export function renderImportError(target: HTMLElement, message: string): void {
  target.replaceChildren();
  target.className = "error";
  const error = document.createElement("strong");
  error.textContent = message;
  target.append(error);
}
