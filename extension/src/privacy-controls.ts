import { MemoraApiClient } from "./api/memora-client";
import type { ContentControlRequest, MemoryStatistics } from "./api/types";
import { loadSettings } from "./settings";

export interface PrivacyDependencies {
  createClient: (backendUrl: string, localToken: string) => Pick<MemoraApiClient, "memoryStatistics" | "clearMemory">;
  loadSettings: typeof loadSettings;
  notifyMemoryCleared: () => Promise<void>;
}

const defaultDependencies: PrivacyDependencies = {
  createClient: (backendUrl, localToken) => new MemoraApiClient(backendUrl, localToken),
  loadSettings,
  notifyMemoryCleared: async () => {
    const message: ContentControlRequest = { type: "MEMORA_MEMORY_CLEARED" };
    const tabs = await chrome.tabs.query({});
    await Promise.allSettled(
      tabs.flatMap((tab) => tab.id === undefined ? [] : [chrome.tabs.sendMessage(tab.id, message)]),
    );
  },
};

export interface PrivacyControls {
  refresh(): Promise<void>;
}

export function initializePrivacyControls(
  root: ParentNode = document,
  dependencies: PrivacyDependencies = defaultDependencies,
): PrivacyControls {
  const conversations = required(root, "#memory-conversations");
  const attachments = required(root, "#memory-attachments");
  const documents = required(root, "#memory-documents");
  const conversationChunks = required(root, "#memory-conversation-chunks");
  const documentChunks = required(root, "#memory-document-chunks");
  const clearButton = required<HTMLButtonElement>(root, "#memory-clear");
  const confirmation = required(root, "#memory-clear-confirmation");
  const cancelButton = required<HTMLButtonElement>(root, "#memory-clear-cancel");
  const confirmButton = required<HTMLButtonElement>(root, "#memory-clear-confirm");
  const status = required(root, "#memory-status");
  let deleting = false;

  const renderCounts = (stats: MemoryStatistics): void => {
    conversations.textContent = String(stats.conversations);
    attachments.textContent = String(stats.attachments);
    documents.textContent = String(stats.documents);
    conversationChunks.textContent = String(stats.conversation_chunks);
    documentChunks.textContent = String(stats.document_chunks);
  };

  const refresh = async (): Promise<void> => {
    try {
      const settings = await dependencies.loadSettings();
      const stats = await dependencies.createClient(
        settings.backendUrl, settings.localToken,
      ).memoryStatistics();
      renderCounts(stats);
      status.className = "helper";
      status.textContent = "";
    } catch {
      status.className = "helper error";
      status.textContent = "Memory statistics are unavailable while the local backend is offline.";
    }
  };

  clearButton.addEventListener("click", () => {
    confirmation.hidden = false;
    clearButton.hidden = true;
    status.textContent = "";
    confirmButton.focus();
  });
  cancelButton.addEventListener("click", () => {
    if (deleting) return;
    confirmation.hidden = true;
    clearButton.hidden = false;
    clearButton.focus();
  });
  confirmButton.addEventListener("click", () => {
    if (deleting) return;
    deleting = true;
    confirmButton.disabled = true;
    cancelButton.disabled = true;
    confirmButton.textContent = "Deleting...";
    status.className = "helper";
    status.textContent = "Clearing Memora's local memory data...";
    void (async () => {
      try {
        const settings = await dependencies.loadSettings();
        await dependencies.createClient(settings.backendUrl, settings.localToken).clearMemory();
        renderCounts({
          conversations: 0, conversation_chunks: 0, attachments: 0,
          documents: 0, document_chunks: 0,
        });
        confirmation.hidden = true;
        clearButton.hidden = false;
        status.className = "helper success";
        status.textContent = "Memora data cleared.";
        try { await dependencies.notifyMemoryCleared(); } catch { /* database deletion already succeeded */ }
      } catch {
        status.className = "helper error";
        status.textContent = "Memora data could not be cleared. Nothing was reported as deleted.";
      } finally {
        deleting = false;
        confirmButton.disabled = false;
        cancelButton.disabled = false;
        confirmButton.textContent = "Delete all Memora data";
      }
    })();
  });

  return { refresh };
}

function required<T extends Element = HTMLElement>(root: ParentNode, selector: string): T {
  const element = root.querySelector<T>(selector);
  if (!element) throw new Error(`Missing privacy control: ${selector}`);
  return element;
}
