import type { BulkImportSummary } from "./api/types";

export function renderImportSummary(target: HTMLElement, summary: BulkImportSummary): void {
  target.replaceChildren();
  target.className = summary.conversations_skipped > 0 ? "partial" : "success";
  const headline = document.createElement("strong");
  headline.textContent = summary.conversations_skipped > 0 ? "Import completed with skips" : "Import complete";
  const details = document.createElement("span");
  details.textContent = `${summary.conversations_found.toLocaleString()} conversations found · ${summary.conversations_imported.toLocaleString()} imported · ${summary.conversations_skipped.toLocaleString()} skipped`;
  const chunks = document.createElement("span");
  chunks.textContent = `${summary.chunks_indexed.toLocaleString()} memory chunks indexed in ${summary.duration_seconds.toFixed(1)}s`;
  target.append(headline, details, chunks);
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
