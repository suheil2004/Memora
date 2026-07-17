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
