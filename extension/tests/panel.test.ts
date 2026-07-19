import { beforeEach, describe, expect, it, vi } from "vitest";

import { MemoraPanel } from "../src/panel";

const response = {
  query: "Where was my model running?",
  context: `[Memora Context]
Source: A Very Long Synthetic Drone Detection Project Conversation Title
User previously discussed:
* User: A Raspberry Pi streams the camera feed.
* User: A Windows laptop with CUDA performs inference.
[/Memora Context]`,
  results: [{
    user_id: "demo-user",
    conversation_id: "conversation-1",
    conversation_title: "A Very Long Synthetic Drone Detection Project Conversation Title",
    chunk_id: "chunk-1",
    score: 0.8234,
    source_message_ids: ["message-1"],
  }],
};

function elements() {
  const root = document.querySelector<HTMLElement>("#memora-extension-root")!.shadowRoot!;
  return {
    root,
    status: root.querySelector<HTMLElement>("#memora-status")!,
    retrieve: root.querySelector<HTMLButtonElement>("#memora-retrieve")!,
    use: root.querySelector<HTMLButtonElement>("#memora-use-context")!,
  };
}

describe("polished Memora panel states", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("renders semantic idle and loading states", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    const ui = elements();
    expect(ui.root.textContent).toContain("Relevant memory");
    expect(ui.retrieve.textContent).toBe("Retrieve memory");
    panel.showLoading();
    expect(ui.status.textContent).toBe("Searching your memory...");
    expect(ui.status.dataset.state).toBe("loading");
    expect(ui.retrieve.disabled).toBe(true);
  });

  it("shows a readable result without raw scores or backend syntax", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults(response);
    const ui = elements();
    expect(ui.root.textContent).toContain(response.results[0].conversation_title);
    expect(ui.root.textContent).toContain("Top match");
    expect(ui.root.textContent).toContain("A Raspberry Pi streams the camera feed.");
    expect(ui.root.textContent).not.toContain("0.8234");
    expect(ui.root.textContent).not.toContain("[Memora Context]");
    expect(ui.use.hidden).toBe(false);
    expect(ui.retrieve.textContent).toBe("Retrieve again");
  });

  it("renders no-match without a context action and keeps errors distinct", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults({ ...response, context: "", results: [] });
    const ui = elements();
    expect(ui.status.textContent).toBe("No relevant memory found for this question.");
    expect(ui.status.dataset.state).toBe("empty");
    expect(ui.use.hidden).toBe(true);
    expect(ui.root.textContent).not.toContain("Top match");
    expect(ui.retrieve.textContent).toBe("Retrieve again");
    panel.showError("Couldn't reach Memora. Check that the local backend is running.");
    expect(ui.status.dataset.state).toBe("error");
    expect(ui.status.textContent).not.toContain("No relevant memory found");
  });

  it("keeps valid results usable and hides the action after insertion", () => {
    const panel = new MemoraPanel(vi.fn(), vi.fn());
    panel.showResults(response);
    let ui = elements();
    expect(ui.status.dataset.state).toBe("results");
    expect(ui.use.hidden).toBe(false);
    panel.showContextUsed();
    ui = elements();
    expect(ui.status.textContent).toContain("Context added to your draft");
    expect(ui.use.hidden).toBe(true);
  });

  it("keeps one live panel so a detached stale instance cannot overwrite it", () => {
    const stalePanel = new MemoraPanel(vi.fn(), vi.fn());
    const currentPanel = new MemoraPanel(vi.fn(), vi.fn());

    expect(document.querySelectorAll("#memora-extension-root")).toHaveLength(1);
    currentPanel.showIdle("Current extension instance");
    stalePanel.showResults(response);

    const ui = elements();
    expect(ui.status.textContent).toBe("Current extension instance");
    expect(ui.root.textContent).not.toContain(response.results[0].conversation_title);
    expect(ui.use.hidden).toBe(true);
  });
});
