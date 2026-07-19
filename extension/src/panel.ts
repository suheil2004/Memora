import type { ContextResponse } from "./api/types";
import { extractContextPoints } from "./context-insertion";

export type PanelState = "idle" | "loading" | "empty" | "error" | "results";

export class MemoraPanel {
  private readonly action: HTMLButtonElement;
  private readonly useAction: HTMLButtonElement;
  private readonly status: HTMLElement;
  private readonly content: HTMLElement;

  constructor(onRetrieve: () => void, onUseContext: () => void) {
    document.getElementById("memora-extension-root")?.remove();
    const host = document.createElement("aside");
    host.id = "memora-extension-root";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `${STYLE}
      <section class="panel" aria-label="Memora relevant memory">
        <header>
          <span class="brand-mark" aria-hidden="true"></span>
          <div><strong>Memora</strong><span>Relevant memory</span></div>
        </header>
        <p id="memora-status" role="status" aria-live="polite">Relevant memory for your current question.</p>
        <div id="memora-content" class="content"></div>
        <div class="actions">
          <button type="button" id="memora-use-context" hidden>Use this context</button>
          <button type="button" id="memora-retrieve" class="secondary">Retrieve memory</button>
        </div>
      </section>`;
    document.body.append(host);
    this.action = required(root, "#memora-retrieve", HTMLButtonElement);
    this.useAction = required(root, "#memora-use-context", HTMLButtonElement);
    this.status = required(root, "#memora-status", HTMLElement);
    this.content = required(root, "#memora-content", HTMLElement);
    this.action.addEventListener("click", onRetrieve);
    this.useAction.addEventListener("click", onUseContext);
  }

  setDraftAvailable(available: boolean): void {
    this.action.dataset.draftAvailable = String(available);
  }

  showIdle(message = "Relevant memory for your current question."): void {
    this.action.textContent = "Retrieve memory";
    this.renderState("idle", message);
  }

  showLoading(): void {
    this.action.disabled = true;
    this.useAction.hidden = true;
    this.renderState("loading", "Searching your memory...");
  }

  showError(message: string): void {
    this.action.disabled = false;
    this.action.textContent = "Try again";
    this.renderState("error", message);
  }

  showInsertionError(message: string): void {
    this.status.dataset.state = "error";
    this.status.textContent = message;
  }

  showContextUsed(alreadyInserted = false): void {
    this.useAction.hidden = true;
    this.action.textContent = "Retrieve again";
    this.status.dataset.state = "results";
    this.status.textContent = alreadyInserted
      ? "This context is already in your draft."
      : "Context added to your draft. Nothing was submitted.";
  }

  showResults(response: ContextResponse): void {
    this.action.disabled = false;
    if (response.results.length === 0 || !response.context.trim()) {
      this.action.textContent = "Retrieve again";
      this.renderState("empty", "No relevant memory found for this question.");
      return;
    }
    const points = extractContextPoints(response.context);
    if (points.length === 0) {
      this.action.textContent = "Retrieve again";
      this.renderState("empty", "No usable memory found. Try making your question a little more specific.");
      return;
    }
    this.renderState("results", "Memory found for your current question.");
    response.results.forEach((result, index) => {
      const card = document.createElement("article");
      const title = document.createElement("strong");
      title.textContent = result.conversation_title || "Previous conversation";
      const relevance = document.createElement("span");
      relevance.textContent = index === 0 ? "Top match" : "Related";
      card.append(title, relevance);
      this.content.append(card);
    });
    const list = document.createElement("ul");
    for (const point of points.slice(0, 8)) {
      const item = document.createElement("li");
      item.textContent = point;
      list.append(item);
    }
    this.content.append(list);
    this.useAction.hidden = false;
    this.action.textContent = "Retrieve again";
  }

  private renderState(state: PanelState, message: string): void {
    this.content.replaceChildren();
    this.useAction.hidden = true;
    this.status.dataset.state = state;
    this.status.textContent = message;
  }
}

function required<T extends Element>(root: ShadowRoot, selector: string, type: { new (): T }): T {
  const element = root.querySelector(selector);
  if (!(element instanceof type)) throw new Error(`Missing panel element: ${selector}`);
  return element;
}

const STYLE = `<style>
  :host {
    all: initial;
    --memora-bg: #ffffff;
    --memora-surface: #f7f7f8;
    --memora-text: #202124;
    --memora-muted: #686b73;
    --memora-border: #e3e4e8;
    --memora-accent: #6256d9;
    --memora-accent-hover: #5146c2;
    --memora-danger: #a43d47;
    --memora-warning: #8a641c;
    --memora-radius: 14px;
    --memora-space-1: 6px;
    --memora-space-2: 10px;
    --memora-space-3: 14px;
    --memora-space-4: 18px;
  }
  * { box-sizing: border-box; }
  .panel { position: fixed; right: 18px; bottom: 18px; z-index: 2147483647; width: min(356px, calc(100vw - 32px)); max-height: min(68vh, 620px); overflow: auto; padding: var(--memora-space-4); border: 1px solid var(--memora-border); border-radius: var(--memora-radius); background: var(--memora-bg); color: var(--memora-text); box-shadow: 0 16px 44px rgba(20, 20, 24, .14); font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  header { display: flex; align-items: center; gap: var(--memora-space-2); margin-bottom: var(--memora-space-3); }
  header div { display: grid; min-width: 0; } header strong { font-size: 16px; line-height: 1.25; letter-spacing: -.01em; } header span { color: var(--memora-muted); font-size: 12px; }
  .brand-mark { width: 10px; height: 10px; flex: 0 0 auto; border-radius: 50%; background: var(--memora-accent); box-shadow: 0 0 0 4px rgba(98, 86, 217, .12); }
  .content { display: grid; gap: var(--memora-space-2); }
  .actions { display: grid; gap: var(--memora-space-1); margin-top: var(--memora-space-3); }
  button { width: 100%; min-height: 38px; border: 1px solid transparent; border-radius: 9px; padding: 8px 12px; background: var(--memora-accent); color: #fff; cursor: pointer; font: inherit; font-weight: 650; transition: background-color .15s ease, border-color .15s ease, transform .15s ease; }
  button:hover:not(:disabled) { background: var(--memora-accent-hover); } button:active:not(:disabled) { transform: translateY(1px); }
  button:focus-visible { outline: 3px solid rgba(98, 86, 217, .28); outline-offset: 2px; }
  button:disabled { opacity: .55; cursor: wait; }
  button.secondary { border-color: var(--memora-border); background: var(--memora-bg); color: var(--memora-text); font-weight: 600; }
  button.secondary:hover:not(:disabled) { background: var(--memora-surface); border-color: #d2d4da; }
  p { margin: 0 0 var(--memora-space-3); color: var(--memora-muted); overflow-wrap: anywhere; }
  p[data-state="loading"]::before { content: ""; display: inline-block; width: 11px; height: 11px; margin-right: 8px; border: 2px solid var(--memora-border); border-top-color: var(--memora-accent); border-radius: 50%; vertical-align: -1px; animation: memora-spin .8s linear infinite; }
  p[data-state="error"] { color: var(--memora-danger); } p[data-state="empty"] { color: var(--memora-warning); }
  article { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--memora-space-2); padding: var(--memora-space-2) 0; border-top: 1px solid var(--memora-border); }
  article strong { min-width: 0; overflow-wrap: anywhere; font-size: 13px; } article span { flex: 0 0 auto; border-radius: 999px; padding: 2px 7px; background: rgba(98, 86, 217, .1); color: #5146c2; font-size: 11px; font-weight: 650; white-space: nowrap; }
  ul { margin: 0; padding: var(--memora-space-2) var(--memora-space-2) var(--memora-space-2) 25px; border-radius: 10px; background: var(--memora-surface); color: #393b40; }
  li { margin: 5px 0; overflow-wrap: anywhere; }
  @keyframes memora-spin { to { transform: rotate(360deg); } }
  @media (max-width: 700px) { .panel { right: 10px; bottom: 10px; width: min(340px, calc(100vw - 20px)); max-height: 58vh; } }
  @media (prefers-reduced-motion: reduce) { button { transition: none; } p[data-state="loading"]::before { animation: none; } }
</style>`;
