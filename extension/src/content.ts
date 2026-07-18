import { ChatGptAdapter } from "./adapters/chatgpt-adapter";
import { requestMemoraContext } from "./messaging";
import { MemoraPanel } from "./panel";
import { requireDraftQuery } from "./query";
import { debug } from "./debug";
import { applyContextSnapshot, createContextSnapshot, type RetrievedContextSnapshot } from "./context-insertion";

const adapter = new ChatGptAdapter();
let panel: MemoraPanel;
let retrievedSnapshot: RetrievedContextSnapshot | null = null;

async function retrieveMemory(): Promise<void> {
  debug("CONTENT", "retrieve button clicked");
  try {
    if (!adapter.isSupportedPage()) throw new Error("This page is not supported by Memora.");
    if (!adapter.hasDraftInput()) throw new Error("ChatGPT input was not found. Reload the page and try again.");
    const query = requireDraftQuery(adapter.getCurrentDraftQuery());
    debug("CONTENT", "extracted query", { queryLength: query.length });
    panel.showLoading();
    const response = await requestMemoraContext(query);
    retrievedSnapshot = createContextSnapshot(response, query);
    panel.showResults(response);
  } catch (error) {
    debug("CONTENT", "retrieval error", error instanceof Error ? error.message : "unknown error");
    panel.showError(friendlyRetrievalError(error));
  }
}

function friendlyRetrievalError(error: unknown): string {
  const message = error instanceof Error ? error.message.toLowerCase() : "";
  if (message.includes("background service")) {
    return "Memora needs to be reloaded. Reload the extension, refresh ChatGPT, and try again.";
  }
  if (message.includes("backend") || message.includes("could not reach")) {
    return "Memora backend is offline. Start the local Memora service and try again.";
  }
  return "Memory retrieval failed. Try again.";
}

function useRetrievedContext(): void {
  debug("CONTENT", "use context button clicked");
  if (!adapter.isSupportedPage()) {
    panel.showInsertionError("This page is no longer supported by Memora.");
    return;
  }
  if (!retrievedSnapshot) {
    panel.showInsertionError("Retrieve usable memory before adding context.");
    return;
  }
  const status = applyContextSnapshot(adapter, retrievedSnapshot);
  if (status === "inserted") panel.showContextUsed();
  else if (status === "already_inserted") panel.showContextUsed(true);
  else if (status === "draft_changed") panel.showInsertionError("The ChatGPT draft changed after retrieval. Retrieve memory again to protect your edits.");
  else if (status === "missing_input") panel.showInsertionError("ChatGPT input was not found. Your draft was not changed.");
  else panel.showInsertionError("Memora could not update the ChatGPT draft. Your original draft was preserved.");
}

function start(): void {
  panel = new MemoraPanel(() => void retrieveMemory(), useRetrievedContext);
  if (!adapter.isSupportedPage()) {
    panel.showError("This page is not supported by Memora.");
    return;
  }
  adapter.observeInputChanges((query) => panel.setDraftAvailable(Boolean(query)));
  if (!adapter.hasDraftInput()) {
    panel.showIdle("Waiting for a question in ChatGPT.");
  }
}

if (document.body) start();
else window.addEventListener("DOMContentLoaded", start, { once: true });
