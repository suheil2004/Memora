import { ChatGptAdapter } from "./adapters/chatgpt-adapter";
import type { BackgroundRequest, BackgroundResponse } from "./api/types";
import { MemoraPanel } from "./panel";
import { requireDraftQuery } from "./query";

const adapter = new ChatGptAdapter();
let panel: MemoraPanel;

async function retrieveMemory(): Promise<void> {
  try {
    if (!adapter.isSupportedPage()) throw new Error("This page is not supported by Memora.");
    if (!adapter.hasDraftInput()) throw new Error("ChatGPT input was not found. Reload the page and try again.");
    const query = requireDraftQuery(adapter.getCurrentDraftQuery());
    panel.showLoading();
    const request: BackgroundRequest = { type: "MEMORA_RETRIEVE", query };
    const response = (await chrome.runtime.sendMessage(request)) as BackgroundResponse | undefined;
    if (!response || typeof response.ok !== "boolean") throw new Error("Memora returned a malformed extension response.");
    if (!response.ok) throw new Error(response.error);
    panel.showResults(response.data);
  } catch (error) {
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
