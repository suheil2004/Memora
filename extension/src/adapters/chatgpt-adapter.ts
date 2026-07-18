import type { ChatSiteAdapter } from "./chat-site-adapter";

export const CHATGPT_INPUT_SELECTORS = [
  "#prompt-textarea",
  'textarea[data-id="root"]',
  'main form [contenteditable="true"][data-virtualkeyboard="true"]',
  'main form [contenteditable="true"]',
] as const;

export class ChatGptAdapter implements ChatSiteAdapter {
  readonly id = "chatgpt";

  constructor(private readonly documentRef: Document = document) {}

  isSupportedPage(location: Location = window.location): boolean {
    return location.hostname === "chatgpt.com" || location.hostname === "chat.openai.com";
  }

  getCurrentDraftQuery(): string | null {
    const input = this.findInput();
    if (!input) return null;
    const value = input instanceof HTMLTextAreaElement ? input.value : input.textContent;
    const normalized = value?.replace(/\u00a0/g, " ").trim() ?? "";
    return normalized || null;
  }

  hasDraftInput(): boolean {
    return this.findInput() !== null;
  }

  setDraftQuery(text: string): boolean {
    const input = this.findInput();
    if (!input || !text.trim()) return false;
    const previous = input instanceof HTMLTextAreaElement ? input.value : input.textContent ?? "";
    try {
      setInputValue(input, text);
      dispatchDraftEvents(input, text);
      input.focus();
      moveCaretToEnd(input, this.documentRef);
      if (this.getCurrentDraftQuery() === normalize(text)) return true;
      setInputValue(input, previous);
      dispatchDraftEvents(input, previous);
      return false;
    } catch {
      setInputValue(input, previous);
      dispatchDraftEvents(input, previous);
      return false;
    }
  }

  observeInputChanges(callback: (query: string | null) => void): () => void {
    const onInput = () => callback(this.getCurrentDraftQuery());
    this.documentRef.addEventListener("input", onInput, true);
    const observer = new MutationObserver(() => callback(this.getCurrentDraftQuery()));
    if (this.documentRef.body) {
      observer.observe(this.documentRef.body, { childList: true, subtree: true });
    }
    callback(this.getCurrentDraftQuery());
    return () => {
      this.documentRef.removeEventListener("input", onInput, true);
      observer.disconnect();
    };
  }

  private findInput(): HTMLElement | null {
    for (const selector of CHATGPT_INPUT_SELECTORS) {
      const element = this.documentRef.querySelector<HTMLElement>(selector);
      if (element) return element;
    }
    return null;
  }
}

function dispatchDraftEvents(input: HTMLElement, text: string): void {
  input.dispatchEvent(new InputEvent("input", {
    bubbles: true,
    composed: true,
    inputType: "insertText",
    data: text,
  }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function setInputValue(input: HTMLElement, text: string): void {
  if (input instanceof HTMLTextAreaElement) {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    if (!setter) throw new Error("Textarea value setter is unavailable");
    setter.call(input, text);
    return;
  }
  input.textContent = text;
}

function moveCaretToEnd(input: HTMLElement, documentRef: Document): void {
  if (input instanceof HTMLTextAreaElement) {
    input.setSelectionRange(input.value.length, input.value.length);
    return;
  }
  const selection = documentRef.getSelection();
  if (!selection) return;
  const range = documentRef.createRange();
  range.selectNodeContents(input);
  range.collapse(false);
  selection.removeAllRanges();
  selection.addRange(range);
}

function normalize(value: string): string {
  return value.replace(/\u00a0/g, " ").trim();
}
