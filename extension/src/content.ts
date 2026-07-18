import { ChatGptAdapter } from "./adapters/chatgpt-adapter";
import { requestMemoraContext } from "./messaging";
import { MemoraPanel } from "./panel";
import { requireDraftQuery } from "./query";
import { debug } from "./debug";

const adapter = new ChatGptAdapter();
let panel: MemoraPanel;

async function retrieveMemory(): Promise<void> {
  debug("CONTENT", "retrieve button clicked");
  try {
    if (!adapter.isSupportedPage()) throw new Error("This page is not supported by Memora.");
    if (!adapter.hasDraftInput()) throw new Error("ChatGPT input was not found. Reload the page and try again.");
    const query = requireDraftQuery(adapter.getCurrentDraftQuery());
    debug("CONTENT", "extracted query", query);
    panel.showLoading();
    panel.showResults(await requestMemoraContext(query));
  } catch (error) {
    debug("CONTENT", "retrieval error", error instanceof Error ? error.message : "unknown error");
    panel.showError(error instanceof Error ? error.message : "Unable to retrieve memory.");
  }
}

function start(): void {
  panel = new MemoraPanel(() => void retrieveMemory());
  if (!adapter.isSupportedPage()) {
    panel.showError("This page is not supported by Memora.");
    return;
  }
  adapter.observeInputChanges((query) => panel.setDraftAvailable(Boolean(query)));
  if (!adapter.hasDraftInput()) {
    panel.showIdle("ChatGPT input not found yet. Memora will keep watching for it.");
  }
}

if (document.body) start();
else window.addEventListener("DOMContentLoaded", start, { once: true });
