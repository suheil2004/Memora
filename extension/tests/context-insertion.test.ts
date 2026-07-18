import { describe, expect, it, vi } from "vitest";

import type { ChatSiteAdapter } from "../src/adapters/chat-site-adapter";
import { applyContextSnapshot, createContextSnapshot } from "../src/context-insertion";

const response = {
  query: "where was I running my model again?",
  context: `[Memora Context]
Source: Drone Detection Project
User previously discussed:
* User: I am building a drone detection system.
* Assistant: What hardware are you using?
* User: A Raspberry Pi 4 streams the camera feed.
* User: My Windows laptop with CUDA performs inference.
[/Memora Context]`,
  results: [{
    user_id: "demo-user",
    conversation_id: "conv-drone",
    conversation_title: "Drone Detection Project",
    chunk_id: "chunk-1",
    score: 0.82,
    source_message_ids: ["message-1"],
  }],
};

class FakeAdapter implements ChatSiteAdapter {
  readonly id = "fake";
  readonly setDraftQuery = vi.fn((text: string) => { this.draft = text; return true; });
  constructor(public draft: string | null) {}
  isSupportedPage(): boolean { return true; }
  hasDraftInput(): boolean { return this.draft !== null; }
  getCurrentDraftQuery(): string | null { return this.draft; }
  observeInputChanges(): () => void { return () => undefined; }
}

describe("explicit context insertion", () => {
  it("creates a compact prompt and preserves the original question", () => {
    const snapshot = createContextSnapshot(response, response.query)!;
    expect(snapshot.prompt).toContain("Relevant context from my previous conversations:");
    expect(snapshot.prompt).toContain("- A Raspberry Pi 4 streams the camera feed.");
    expect(snapshot.prompt).not.toContain("What hardware are you using?");
    expect(snapshot.prompt).not.toContain("[Memora Context]");
    expect(snapshot.prompt).toContain(`My question:\n${response.query}`);
  });

  it("inserts once and prevents duplicate insertion", () => {
    const snapshot = createContextSnapshot(response, response.query)!;
    const adapter = new FakeAdapter(response.query);
    expect(applyContextSnapshot(adapter, snapshot)).toBe("inserted");
    expect(adapter.setDraftQuery).toHaveBeenCalledOnce();
    expect(applyContextSnapshot(adapter, snapshot)).toBe("already_inserted");
    expect(adapter.setDraftQuery).toHaveBeenCalledOnce();
  });

  it("refuses changed drafts, missing inputs, and adapter failures", () => {
    const snapshot = createContextSnapshot(response, response.query)!;
    const changed = new FakeAdapter("user edited this after retrieval");
    expect(applyContextSnapshot(changed, snapshot)).toBe("draft_changed");
    expect(changed.setDraftQuery).not.toHaveBeenCalled();

    expect(applyContextSnapshot(new FakeAdapter(null), snapshot)).toBe("missing_input");

    const failed = new FakeAdapter(response.query);
    failed.setDraftQuery.mockImplementation(() => false);
    expect(applyContextSnapshot(failed, snapshot)).toBe("failed");
  });
});
