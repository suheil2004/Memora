import { beforeEach, describe, expect, it, vi } from "vitest";

import { LOADING_STAGE_DELAYS_MS, LOADING_STAGE_MESSAGES, MemoraPanel } from "../src/panel";
import type { ContextResponse } from "../src/api/types";

const response: ContextResponse = {
  query: "Where was my model running?",
  context: `[Memora Context]
Source: A Very Long Synthetic Drone Detection Project Conversation Title
User previously discussed:
* User: A Raspberry Pi streams the camera feed.
* User: A Windows laptop with CUDA performs inference.
* Assistant: RAW_LONG_ASSISTANT_DIALOGUE_MUST_NOT_RENDER
[/Memora Context]`,
  results: [{
    user_id: "demo-user",
    conversation_id: "conversation-1",
    conversation_title: "A Very Long Synthetic Drone Detection Project Conversation Title",
    chunk_id: "chunk-1",
    score: 0.8234,
    source_message_ids: ["message-1"],
  }],
  memories: [{ thread_id: "thread-1", title: "Drone Detection Project", subject: "user",
    summary: "The camera pipeline is split across two devices.",
    key_details: ["A Raspberry Pi streams the camera feed.", "A Windows laptop with CUDA performs inference."],
    sources: [{ type: "conversation", conversation_id: "conversation-1", conversation_title: "A Very Long Synthetic Drone Detection Project Conversation Title" }],
    used_fallback: false, latest_timestamp: "2026-01-15T12:00:00Z" }],
};

function elements() {
  const root = document.querySelector<HTMLElement>("#memora-extension-root")!.shadowRoot!;
  return {
    root,
    status: root.querySelector<HTMLElement>("#memora-status")!,
    retrieve: root.querySelector<HTMLButtonElement>("#memora-retrieve")!,
    bubble: root.querySelector<HTMLButtonElement>("#memora-bubble")!,
    panel: root.querySelector<HTMLElement>("#memora-panel")!,
    minimize: root.querySelector<HTMLButtonElement>("#memora-minimize")!,
    sort: root.querySelector<HTMLSelectElement>("#memora-sort")!,
    sortControl: root.querySelector<HTMLElement>("#memora-sort-control")!,
    toolbar: root.querySelector<HTMLElement>("#memora-results-toolbar")!,
    displayedQuery: root.querySelector<HTMLElement>("#memora-displayed-query")!,
    searchCurrent: root.querySelector<HTMLButtonElement>("#memora-search-current")!,
    clearResults: root.querySelector<HTMLButtonElement>("#memora-clear-results")!,
    uses: root.querySelectorAll<HTMLButtonElement>("article button:not(.link-button)"),
  };
}

describe("polished Memora panel states", () => {
  let storedPosition: Record<string, unknown>;
  let storageSet: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    document.body.innerHTML = "";
    Object.defineProperty(window, "innerWidth", { value: 1000, configurable: true });
    Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
    storedPosition = {};
    storageSet = vi.fn(async (value: Record<string, unknown>) => { Object.assign(storedPosition, value); });
    Object.defineProperty(globalThis, "chrome", { configurable: true, value: {
      storage: { local: {
        get: vi.fn(async () => ({ ...storedPosition })),
        set: storageSet,
      } },
    } });
  });

  it("starts as a compact collapsed bubble away from composer controls", () => {
    new MemoraPanel(vi.fn(), vi.fn());
    const ui = elements();
    expect(ui.panel.hidden).toBe(true);
    expect(ui.bubble.getAttribute("aria-label")).toBe("Open Memora");
    expect(ui.bubble.title).toBe("Open Memora");
    expect(ui.bubble.textContent).toBe("Memora");
    expect(ui.bubble.querySelector("svg")).not.toBeNull();
    expect(ui.bubble.style.left).toBe("876px");
    expect(Number.parseInt(ui.bubble.style.top)).toBeGreaterThan(250);
    expect(Number.parseInt(ui.bubble.style.top)).toBeLessThan(500);
    expect(ui.toolbar.hidden).toBe(true);
  });

  it("uses the premium white full-brand trigger treatment", () => {
    new MemoraPanel(vi.fn(), vi.fn());
    const ui = elements();
    const styles = ui.root.querySelector("style")?.textContent ?? "";
    expect(styles).toContain("width:108px; height:42px");
    expect(styles).toContain("background:#fff; color:#111");
    expect(styles).toContain("border:1px solid #e5e5e5");
    expect(styles).not.toContain("linear-gradient");
    expect(ui.bubble.textContent).not.toBe("M");
  });

  it("expands inward, minimizes, and preserves retrieved memories", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    const ui = elements();
    ui.bubble.click();
    expect(ui.panel.hidden).toBe(false);
    expect(ui.panel.dataset.direction).toBe("left");
    panel.showResults(response);
    expect(ui.root.textContent).toContain("Drone Detection Project");
    ui.minimize.click();
    expect(ui.panel.hidden).toBe(true);
    ui.bubble.click();
    expect(ui.panel.hidden).toBe(false);
    expect(ui.root.textContent).toContain("Drone Detection Project");
  });

  it("persists drag position and clamps restored coordinates", async () => {
    new MemoraPanel(vi.fn(), vi.fn());
    let ui = elements();
    ui.bubble.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, button: 0, clientX: 950, clientY: 320 }));
    window.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 420, clientY: 260 }));
    window.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
    await Promise.resolve();
    expect(storageSet).toHaveBeenCalledWith({ memoraBubblePosition: { x: 346, y: 255 } });

    storedPosition.memoraBubblePosition = { x: 50_000, y: 50_000 };
    new MemoraPanel(vi.fn(), vi.fn());
    await Promise.resolve();
    await Promise.resolve();
    ui = elements();
    expect(ui.bubble.style.left).toBe("876px");
    expect(ui.bubble.style.top).toBe("646px");
  });

  it("opens right from a restored left-side position and supports keyboard activation", async () => {
    storedPosition.memoraBubblePosition = { x: 24, y: 280 };
    new MemoraPanel(vi.fn(), vi.fn());
    await Promise.resolve();
    await Promise.resolve();
    const ui = elements();
    ui.bubble.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }));
    expect(ui.panel.hidden).toBe(false);
    expect(ui.panel.dataset.direction).toBe("right");
    expect(ui.bubble.getAttribute("aria-expanded")).toBe("true");
    ui.minimize.click();
    ui.bubble.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: " " }));
    expect(ui.panel.hidden).toBe(false);
  });

  it("renders semantic idle and loading states", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    const ui = elements();
    expect(ui.root.textContent).toContain("Relevant memories");
    expect(ui.retrieve.textContent).toBe("Retrieve memory");
    panel.showLoading();
    expect(ui.status.textContent).toBe(LOADING_STAGE_MESSAGES[0]);
    expect(ui.status.dataset.state).toBe("loading");
    expect(ui.retrieve.disabled).toBe(true);
  });

  it("advances loading copy calmly and clears stale timers after success", async () => {
    vi.useFakeTimers();
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showLoading();
    let ui = elements();
    expect(ui.status.textContent).toBe(LOADING_STAGE_MESSAGES[0]);
    await vi.advanceTimersByTimeAsync(LOADING_STAGE_DELAYS_MS[0]);
    expect(ui.status.textContent).toBe(LOADING_STAGE_MESSAGES[1]);
    await vi.advanceTimersByTimeAsync(LOADING_STAGE_DELAYS_MS[1] - LOADING_STAGE_DELAYS_MS[0]);
    expect(ui.status.textContent).toBe(LOADING_STAGE_MESSAGES[2]);

    panel.showResults(response);
    ui = elements();
    expect(ui.status.textContent).toBe("Relevant memories found.");
    await vi.advanceTimersByTimeAsync(60_000);
    expect(ui.status.textContent).toBe("Relevant memories found.");
    expect(ui.retrieve.disabled).toBe(false);
    vi.useRealTimers();
  });

  it("clears loading timers on failure and restarts stages for a later request", async () => {
    vi.useFakeTimers();
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showLoading();
    await vi.advanceTimersByTimeAsync(LOADING_STAGE_DELAYS_MS[0]);
    expect(elements().status.textContent).toBe(LOADING_STAGE_MESSAGES[1]);
    panel.showError("Authentication failed. Check your token.");
    expect(elements().retrieve.disabled).toBe(false);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(elements().status.textContent).toBe("Authentication failed. Check your token.");

    panel.showLoading();
    expect(elements().status.textContent).toBe(LOADING_STAGE_MESSAGES[0]);
    await vi.advanceTimersByTimeAsync(LOADING_STAGE_DELAYS_MS[0]);
    expect(elements().status.textContent).toBe(LOADING_STAGE_MESSAGES[1]);
    elements().bubble.click();
    elements().minimize.click();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(elements().status.textContent).toBe(LOADING_STAGE_MESSAGES[1]);
    elements().bubble.click();
    expect(elements().panel.hidden).toBe(false);
    vi.useRealTimers();
  });

  it("shows a readable result without raw scores or backend syntax", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults(response);
    const ui = elements();
    expect(ui.root.textContent).toContain(response.memories[0].title);
    expect(ui.root.textContent).toContain("Top memory");
    expect(ui.root.textContent).toContain("A Raspberry Pi streams the camera feed.");
    expect(ui.root.textContent).not.toContain("0.8234");
    expect(ui.root.textContent).not.toContain("[Memora Context]");
    expect(ui.root.textContent).not.toContain("RAW_LONG_ASSISTANT_DIALOGUE_MUST_NOT_RENDER");
    expect(ui.uses).toHaveLength(1);
    expect(ui.retrieve.textContent).toBe("Retrieve again");
    expect(ui.root.textContent).toContain("Discussed Jan 2026");
    expect(ui.toolbar.hidden).toBe(false);
    expect(ui.displayedQuery.textContent).toBe(response.query);
    expect(ui.displayedQuery.title).toBe(response.query);
  });

  it("keeps the successful query sticky while the live draft changes", () => {
    const retrieve = vi.fn();
    const panel = new MemoraPanel(retrieve, vi.fn());
    panel.setDraftAvailable(true);
    panel.showResults(response, "Tell me about my drone detection project");
    let ui = elements();
    expect(ui.displayedQuery.textContent).toBe("Tell me about my drone detection project");
    panel.setDraftAvailable(true);
    expect(ui.displayedQuery.textContent).toBe("Tell me about my drone detection project");
    expect((ui.root.querySelector("style")?.textContent ?? "")).toContain("position:sticky");
    ui.searchCurrent.click();
    expect(retrieve).toHaveBeenCalledTimes(1);
  });

  it("replaces cards, resets scrolling, and disables repeated search while loading", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.setDraftAvailable(true);
    panel.showResults(response);
    let ui = elements();
    ui.panel.scrollTop = 240;
    panel.showLoading();
    ui = elements();
    expect(ui.panel.scrollTop).toBe(0);
    expect(ui.searchCurrent.disabled).toBe(true);
    expect(ui.root.textContent).not.toContain("Drone Detection Project");
    panel.showResults({ ...response, query: "Plan an event", memories: [{ ...response.memories[0], thread_id: "event", title: "Event planning" }] });
    ui = elements();
    expect(ui.root.textContent).toContain("Event planning");
    expect(Array.from(ui.root.querySelectorAll(".card-heading strong"), (node) => node.textContent))
      .toEqual(["Event planning"]);
    expect(ui.displayedQuery.textContent).toBe("Plan an event");
  });

  it("does not request an empty current prompt and clears results non-destructively", () => {
    const retrieve = vi.fn();
    const clear = vi.fn();
    const use = vi.fn();
    const panel = new MemoraPanel(retrieve, use, clear);
    panel.setDraftAvailable(false);
    panel.showResults(response);
    let ui = elements();
    expect(ui.searchCurrent.disabled).toBe(true);
    ui.searchCurrent.click();
    expect(retrieve).not.toHaveBeenCalled();
    ui.panel.scrollTop = 180;
    ui.clearResults.click();
    ui = elements();
    expect(clear).toHaveBeenCalledTimes(1);
    expect(retrieve).not.toHaveBeenCalled();
    expect(use).not.toHaveBeenCalled();
    expect(ui.toolbar.hidden).toBe(true);
    expect(ui.root.querySelectorAll("article.memory-card")).toHaveLength(0);
    expect(ui.status.dataset.state).toBe("idle");
    expect(ui.panel.scrollTop).toBe(0);
  });

  it("keeps sorting functional after a repeated retrieval", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    const older = { ...response.memories[0], thread_id: "older", title: "Older best", latest_timestamp: "2025-01-01T00:00:00Z" };
    const newer = { ...response.memories[0], thread_id: "newer", title: "Newer related", latest_timestamp: "2026-06-01T00:00:00Z" };
    panel.showResults(response);
    panel.showLoading();
    panel.showResults({ ...response, query: "Newest prompt", memories: [older, newer] });
    const ui = elements();
    ui.sort.value = "recent";
    ui.sort.dispatchEvent(new Event("change", { bubbles: true }));
    expect(Array.from(ui.root.querySelectorAll(".card-heading strong"), (node) => node.textContent))
      .toEqual(["Newer related", "Older best"]);
  });

  it("defaults to best match and reorders existing cards by trusted timestamp", () => {
    const retrieve = vi.fn();
    const useMemory = vi.fn();
    const panel = new MemoraPanel(retrieve, useMemory);
    const older = { ...response.memories[0], thread_id: "best", title: "Best current match",
      latest_timestamp: "2025-03-01T00:00:00Z" };
    const newer = { ...response.memories[0], thread_id: "newer", title: "Newer related memory",
      latest_timestamp: "2026-06-01T00:00:00Z" };
    panel.showResults({ ...response, memories: [older, newer] });
    let ui = elements();
    const titles = () => Array.from(ui.root.querySelectorAll(".card-heading strong"), (node) => node.textContent);

    expect(ui.sort.value).toBe("best");
    expect(titles()).toEqual(["Best current match", "Newer related memory"]);
    ui.sort.value = "recent";
    ui.sort.dispatchEvent(new Event("change", { bubbles: true }));
    ui = elements();
    expect(titles()).toEqual(["Newer related memory", "Best current match"]);
    expect(retrieve).not.toHaveBeenCalled();

    ui.uses[0]?.click();
    expect(useMemory).toHaveBeenCalledWith(newer);
  });

  it("degrades gracefully without timestamps and keeps sorted state after minimize", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    const withoutTimestamp = { ...response.memories[0], latest_timestamp: undefined };
    panel.showResults({ ...response, memories: [withoutTimestamp] });
    let ui = elements();
    expect(ui.sortControl.hidden).toBe(false);
    expect(ui.root.querySelectorAll(".timestamp:not([hidden])")).toHaveLength(0);
    ui.sort.value = "recent";
    ui.sort.dispatchEvent(new Event("change", { bubbles: true }));
    ui.bubble.click();
    ui.minimize.click();
    ui.bubble.click();
    ui = elements();
    expect(ui.sort.value).toBe("recent");
    expect(ui.root.textContent).toContain("Drone Detection Project");
  });

  it("renders no-match without a context action and keeps errors distinct", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults({ ...response, context: "", results: [], memories: [] });
    const ui = elements();
    expect(ui.status.textContent).toBe("No relevant memory found for this question.");
    expect(ui.status.dataset.state).toBe("empty");
    expect(ui.uses).toHaveLength(0);
    expect(ui.root.textContent).not.toContain("Top memory");
    expect(ui.retrieve.textContent).toBe("Retrieve again");
    panel.showError("Couldn't reach Memora. Check that the local backend is running.");
    expect(ui.status.dataset.state).toBe("error");
    expect(ui.status.textContent).not.toContain("No relevant memory found");
  });

  it("keeps valid results individually usable after insertion", () => {
    const useMemory = vi.fn();
    const panel = new MemoraPanel(vi.fn(), useMemory);
    panel.showResults(response);
    let ui = elements();
    expect(ui.status.dataset.state).toBe("results");
    ui.uses[0]?.click();
    expect(useMemory).toHaveBeenCalledWith(response.memories[0]);
    panel.showMemoryUsed("thread-1");
    ui = elements();
    expect(ui.status.textContent).toContain("Memory added to your draft");
    expect(ui.uses[0]?.disabled).toBe(true);
  });

  it("clears retrieved and used state without changing composer content", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults(response);
    panel.showMemoryUsed("thread-1");
    panel.clearMemories();
    const ui = elements();
    expect(ui.root.textContent).not.toContain("Drone Detection Project");
    expect(ui.uses).toHaveLength(0);
    expect(ui.retrieve.textContent).toBe("Retrieve memory");
    expect(ui.status.textContent).toContain("Memora data cleared");
  });

  it("keeps one live panel so a detached stale instance cannot overwrite it", () => {
    const stalePanel = new MemoraPanel(vi.fn(), vi.fn());
    const currentPanel = new MemoraPanel(vi.fn(), vi.fn());

    expect(document.querySelectorAll("#memora-extension-root")).toHaveLength(1);
    currentPanel.showIdle("Current extension instance");
    stalePanel.showResults(response);

    const ui = elements();
    expect(ui.status.textContent).toBe("Current extension instance");
    expect(ui.root.textContent).not.toContain(response.memories[0].title);
    expect(ui.uses).toHaveLength(0);
  });

  it("renders at most five separate cards with related details collapsed", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    const memories = Array.from({ length: 7 }, (_, index) => ({
      ...response.memories[0], thread_id: `thread-${index}`, title: `Memory ${index}`,
    }));
    panel.showResults({ ...response, memories });
    const ui = elements();
    expect(ui.root.querySelectorAll("article.memory-card")).toHaveLength(5);
    expect(ui.root.querySelectorAll(".details:not([hidden])")).toHaveLength(1);
    expect(ui.root.querySelectorAll("button.link-button")).toHaveLength(4);
  });

  it("shows partial success when a brief used fallback synthesis", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults({ ...response, memories: [{ ...response.memories[0], used_fallback: true }] });
    const ui = elements();
    expect(ui.status.dataset.state).toBe("partial");
    expect(ui.status.textContent).toContain("local fallback");
    expect(ui.uses).toHaveLength(1);
  });

  it("keeps user running and girlfriend Pilates as separate sourced cards", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults({ ...response, memories: [
      { ...response.memories[0], thread_id: "running", title: "Running progression", subject: "user" },
      { ...response.memories[0], thread_id: "pilates", title: "Pilates plan", subject: "girlfriend",
        summary: "A separate Pilates routine.", sources: [{ type: "conversation", conversation_id: "pilates-conv", conversation_title: "Pilates workout discussion" }] },
    ] });
    const ui = elements();
    expect(ui.root.querySelectorAll("article.memory-card")).toHaveLength(2);
    expect(ui.root.textContent).toContain("Running progression");
    expect(ui.root.textContent).toContain("Pilates plan");
    ui.root.querySelector<HTMLButtonElement>("button.link-button")?.click();
    expect(ui.root.textContent).toContain("About: Girlfriend");
    expect(ui.root.textContent).toContain("Pilates workout discussion");
  });

  it("renders compact trusted PDF page provenance without paths", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults({ ...response, memories: [{ ...response.memories[0], sources: [{
      type: "document", document_id: "doc-1", filename: "practice.pdf",
      page_start: 2, page_end: 4, parent_conversation_id: "conversation-1",
    }] }] });
    const ui = elements();
    expect(ui.root.textContent).toContain("PDF: practice.pdf · pp. 2-4");
    expect(ui.root.textContent).not.toContain("C:\\");
  });

  it("renders attachment metadata as text without interpreting HTML", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults({ ...response, memories: [{ ...response.memories[0], sources: [{
      type: "attachment", attachment_id: "attachment-1",
      filename: "<img src=x onerror=alert(1)>.pdf", mime_type: "application/pdf",
      conversation_id: "conversation-1", message_id: "message-1",
      binary_resolution_status: "metadata_only",
    }] }] });
    const ui = elements();
    expect(ui.root.textContent).toContain("Attachment: <img src=x onerror=alert(1)>.pdf");
    expect(ui.root.querySelector("img")).toBeNull();
  });
});
