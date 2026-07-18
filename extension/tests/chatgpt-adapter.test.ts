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

  it("updates a textarea, emits events, preserves focus, and never submits", () => {
    document.body.innerHTML = '<form><textarea id="prompt-textarea">original question</textarea><button id="send" type="submit">Send</button></form>';
    const adapter = new ChatGptAdapter(document);
    const input = document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!;
    const send = document.querySelector<HTMLButtonElement>("#send")!;
    const inputEvent = vi.fn();
    const changeEvent = vi.fn();
    const clickEvent = vi.fn();
    input.addEventListener("input", inputEvent);
    input.addEventListener("change", changeEvent);
    send.addEventListener("click", clickEvent);

    expect(adapter.setDraftQuery("context\n\noriginal question")).toBe(true);
    expect(input.value).toBe("context\n\noriginal question");
    expect(document.activeElement).toBe(input);
    expect(inputEvent).toHaveBeenCalledOnce();
    expect(changeEvent).toHaveBeenCalledOnce();
    expect(clickEvent).not.toHaveBeenCalled();
  });

  it("updates a contenteditable ChatGPT input", () => {
    document.body.innerHTML = '<main><form><div id="prompt-textarea" contenteditable="true">original question</div></form></main>';
    const adapter = new ChatGptAdapter(document);
    const input = document.querySelector<HTMLElement>("#prompt-textarea")!;
    const inputEvent = vi.fn();
    input.addEventListener("input", inputEvent);

    expect(adapter.setDraftQuery("context\n\noriginal question")).toBe(true);
    expect(input.textContent).toBe("context\n\noriginal question");
    expect(document.activeElement).toBe(input);
    expect(inputEvent).toHaveBeenCalledOnce();
  });

  it("fails without changing anything when the input is missing", () => {
    const adapter = new ChatGptAdapter(document);
    expect(adapter.setDraftQuery("context")).toBe(false);
    expect(document.body.textContent).toBe("");
  });
});
