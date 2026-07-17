import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatGptAdapter } from "../src/adapters/chatgpt-adapter";

describe("ChatGptAdapter", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("recognizes only supported ChatGPT hosts", () => {
    const adapter = new ChatGptAdapter(document);
    expect(adapter.hasDraftInput()).toBe(false);
    expect(adapter.isSupportedPage({ hostname: "chatgpt.com" } as Location)).toBe(true);
    expect(adapter.isSupportedPage({ hostname: "example.com" } as Location)).toBe(false);
  });

  it("reads and trims the draft without modifying it", () => {
    document.body.innerHTML = '<textarea id="prompt-textarea">  Where is inference running?  </textarea>';
    const input = document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!;
    const adapter = new ChatGptAdapter(document);
    expect(adapter.hasDraftInput()).toBe(true);

    expect(adapter.getCurrentDraftQuery()).toBe("Where is inference running?");
    expect(input.value).toBe("  Where is inference running?  ");
  });

  it("returns null when the input is absent and observes local input changes", () => {
    document.body.innerHTML = "";
    const adapter = new ChatGptAdapter(document);
    expect(adapter.hasDraftInput()).toBe(false);
    expect(adapter.getCurrentDraftQuery()).toBeNull();

    document.body.innerHTML = '<textarea id="prompt-textarea"></textarea>';
    const callback = vi.fn();
    const stop = adapter.observeInputChanges(callback);
    const input = document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!;
    input.value = "new draft";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    expect(callback).toHaveBeenLastCalledWith("new draft");
    stop();
  });
});
