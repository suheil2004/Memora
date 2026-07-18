import type { ContextResponse } from "./api/types";
import { extractContextPoints } from "./context-insertion";

export type PanelState = "idle" | "loading" | "empty" | "error" | "results";

export class MemoraPanel {
  private readonly action: HTMLButtonElement;
  private readonly useAction: HTMLButtonElement;
  private readonly status: HTMLElement;
  private readonly content: HTMLElement;

  constructor(onRetrieve: () => void, onUseContext: () => void) {
    const host = document.createElement("aside");
    host.id = "memora-extension-root";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `${STYLE}
      <section class="panel" aria-label="Memora relevant memory">
        <header><strong>Memora</strong><span>Relevant Memory</span></header>
        <button type="button" id="memora-retrieve">Retrieve memory</button>
        <button type="button" id="memora-use-context" class="secondary" hidden>Use this context</button>
        <p id="memora-status" role="status">Type a draft, then retrieve memory.</p>
        <div id="memora-content"></div>
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

  showIdle(message = "Type a draft, then retrieve memory."): void {
    this.renderState("idle", message);
  }

  showLoading(): void {
    this.action.disabled = true;
    this.useAction.hidden = true;
    this.renderState("loading", "Searching your memory…");
  }

  showError(message: string): void {
    this.action.disabled = false;
    this.renderState("error", message);
  }

  showInsertionError(message: string): void {
    this.status.dataset.state = "error";
    this.status.textContent = message;
  }

  showContextUsed(alreadyInserted = false): void {
    this.useAction.hidden = true;
    this.status.dataset.state = "results";
    this.status.textContent = alreadyInserted ? "This context is already in the draft." : "Context added to the draft. Nothing was submitted.";
  }

  showResults(response: ContextResponse): void {
    this.action.disabled = false;
    if (response.results.length === 0 || !response.context.trim()) {
      this.renderState("empty", "No relevant memory was found.");
      return;
    }
    const points = extractContextPoints(response.context);
    if (points.length === 0) {
      this.renderState("empty", "No usable memory context was found.");
      return;
    }
    this.renderState("results", `${response.results.length} relevant source${response.results.length === 1 ? "" : "s"}.`);
    for (const result of response.results) {
      const card = document.createElement("article");
      const title = document.createElement("strong");
      title.textContent = result.conversation_title || "Previous conversation";
      const score = document.createElement("span");
      score.textContent = `Relevance: ${result.score.toFixed(3)}`;
      card.append(title, score);
      this.content.append(card);
    }
    const list = document.createElement("ul");
    for (const point of points.slice(0, 8)) {
      const item = document.createElement("li");
      item.textContent = point;
      list.append(item);
    }
    this.content.append(list);
    this.useAction.hidden = false;
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
  :host { all: initial; }
  .panel { position: fixed; right: 18px; bottom: 18px; z-index: 2147483647; width: 330px; max-height: 70vh; overflow: auto; box-sizing: border-box; padding: 14px; border: 1px solid #d4d4d8; border-radius: 12px; background: #fff; color: #18181b; box-shadow: 0 12px 32px rgba(0,0,0,.18); font: 14px/1.4 system-ui, sans-serif; }
  header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; } header strong { font-size: 18px; color: #2563eb; } header span { color: #71717a; font-size: 12px; }
  button { width: 100%; border: 0; border-radius: 8px; padding: 9px 12px; background: #2563eb; color: white; cursor: pointer; font-weight: 650; } button:disabled { opacity: .6; cursor: wait; }
  button.secondary { margin-top: 8px; background: #18181b; }
  p { margin: 10px 0 0; color: #52525b; } p[data-state="error"] { color: #b91c1c; } p[data-state="empty"] { color: #854d0e; }
  article { display: flex; justify-content: space-between; gap: 8px; margin-top: 12px; padding-top: 10px; border-top: 1px solid #e4e4e7; } article span { color: #71717a; font-size: 12px; white-space: nowrap; }
  ul { margin: 10px 0 0; padding-left: 20px; } li { margin: 5px 0; }
</style>`;
