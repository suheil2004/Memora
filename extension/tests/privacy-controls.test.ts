import { beforeEach, describe, expect, it, vi } from "vitest";

import { initializePrivacyControls, type PrivacyDependencies } from "../src/privacy-controls";
import { MemoraPanel } from "../src/panel";
import type { ContextResponse } from "../src/api/types";

const stats = {
  conversations: 867, conversation_chunks: 7751, attachments: 1505,
  documents: 33, document_chunks: 1011,
};

function fixture(): void {
  document.body.innerHTML = `
    <span id="memory-conversations">—</span><span id="memory-attachments">—</span>
    <span id="memory-documents">—</span><span id="memory-conversation-chunks">—</span>
    <span id="memory-document-chunks">—</span>
    <button id="memory-clear">Clear Memora data</button>
    <div id="memory-clear-confirmation" hidden>
      <button id="memory-clear-cancel">Cancel</button>
      <button id="memory-clear-confirm">Delete all Memora data</button>
    </div>
    <p id="memory-status"></p>`;
}

function dependencies(
  memoryStatistics: () => Promise<typeof stats> = vi.fn(async () => stats),
  clearMemory: () => Promise<{ cleared: true; rows_deleted: number }> = vi.fn(
    async () => ({ cleared: true as const, rows_deleted: 10 }),
  ),
  notifyMemoryCleared: () => Promise<void> = vi.fn(async () => undefined),
): PrivacyDependencies {
  return {
    loadSettings: vi.fn(async () => ({
      backendUrl: "http://127.0.0.1:8765", localToken: "synthetic-token-000000000", topK: 5,
    })),
    createClient: () => ({ memoryStatistics, clearMemory }),
    notifyMemoryCleared,
  };
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe("Privacy & Memory controls", () => {
  beforeEach(() => fixture());

  it("renders aggregate statistics without private metadata", async () => {
    const deps = dependencies();
    const controls = initializePrivacyControls(document, deps);
    await controls.refresh();
    expect(document.querySelector("#memory-conversations")?.textContent).toBe("867");
    expect(document.querySelector("#memory-attachments")?.textContent).toBe("1505");
    expect(document.querySelector("#memory-documents")?.textContent).toBe("33");
    expect(document.body.textContent).not.toContain("conversation-title");
    expect(document.body.textContent).not.toContain("secret-token");
    expect(document.body.textContent).not.toContain(".pdf");
  });

  it("requires confirmation and cancel performs no request", () => {
    const clearMemory = vi.fn(async () => ({ cleared: true as const, rows_deleted: 1 }));
    initializePrivacyControls(document, dependencies(undefined, clearMemory));
    const clear = document.querySelector<HTMLButtonElement>("#memory-clear")!;
    const confirmation = document.querySelector<HTMLElement>("#memory-clear-confirmation")!;
    clear.click();
    expect(clearMemory).not.toHaveBeenCalled();
    expect(confirmation.hidden).toBe(false);
    document.querySelector<HTMLButtonElement>("#memory-clear-cancel")!.click();
    expect(clearMemory).not.toHaveBeenCalled();
    expect(confirmation.hidden).toBe(true);
  });

  it("sends one destructive request and blocks duplicate clicks while deleting", async () => {
    let resolveDelete!: () => void;
    const pending = new Promise<void>((resolve) => { resolveDelete = resolve; });
    const clearMemory = vi.fn(async () => {
      await pending;
      return { cleared: true as const, rows_deleted: 5 };
    });
    initializePrivacyControls(document, dependencies(undefined, clearMemory));
    document.querySelector<HTMLButtonElement>("#memory-clear")!.click();
    const confirm = document.querySelector<HTMLButtonElement>("#memory-clear-confirm")!;
    confirm.click();
    confirm.click();
    await flush();
    expect(clearMemory).toHaveBeenCalledOnce();
    expect(confirm.disabled).toBe(true);
    resolveDelete();
    await flush();
    expect(confirm.disabled).toBe(false);
  });

  it("resets counts and clears displayed MemoryBrief state after success", async () => {
    const response: ContextResponse = {
      query: "drone", context: "context", results: [], memories: [{
        thread_id: "thread", title: "Drone memory", subject: "user", summary: "Summary",
        key_details: ["Detail"], sources: [{
          type: "conversation", conversation_id: "conversation", conversation_title: "Drone",
        }], used_fallback: false,
      }],
    };
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults(response);
    const notify = vi.fn(async () => panel.clearMemories());
    initializePrivacyControls(document, dependencies(undefined, undefined, notify));
    document.querySelector<HTMLButtonElement>("#memory-clear")!.click();
    document.querySelector<HTMLButtonElement>("#memory-clear-confirm")!.click();
    await flush();
    expect(document.querySelector("#memory-conversations")?.textContent).toBe("0");
    expect(document.querySelector("#memory-status")?.textContent).toBe("Memora data cleared.");
    expect(notify).toHaveBeenCalledOnce();
    const panelRoot = document.querySelector<HTMLElement>("#memora-extension-root")!.shadowRoot!;
    expect(panelRoot.textContent).not.toContain("Drone memory");
    expect(panelRoot.textContent).toContain("Memora data cleared");
  });

  it("reports failure and restores usable controls", async () => {
    const clearMemory = vi.fn(async () => { throw new Error("private SQL detail"); });
    initializePrivacyControls(document, dependencies(undefined, clearMemory));
    document.querySelector<HTMLButtonElement>("#memory-clear")!.click();
    const confirm = document.querySelector<HTMLButtonElement>("#memory-clear-confirm")!;
    confirm.click();
    await flush();
    expect(confirm.disabled).toBe(false);
    expect(document.querySelector("#memory-status")?.textContent).toContain("could not be cleared");
    expect(document.body.textContent).not.toContain("private SQL detail");
    confirm.click();
    await flush();
    expect(clearMemory).toHaveBeenCalledTimes(2);
  });
});
