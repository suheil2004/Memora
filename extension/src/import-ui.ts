import type { BulkImportSummary } from "./api/types";

export function renderImportSummary(target: HTMLElement, summary: BulkImportSummary): void {
  target.replaceChildren();
  const headline = document.createElement("strong");
  headline.textContent = `Imported ${summary.conversations_imported} of ${summary.conversations_found} conversations`;
  const details = document.createElement("span");
  details.textContent = `${summary.messages_imported} messages, ${summary.chunks_indexed} chunks, ${summary.conversations_skipped} skipped (${summary.duration_seconds.toFixed(1)}s)`;
  target.append(headline, details);
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
  const error = document.createElement("strong");
  error.textContent = message;
  target.append(error);
}
