import type { ContextResponse, MemoryBrief } from "./api/types";

export type PanelState = "idle" | "loading" | "empty" | "error" | "results" | "partial";

interface BubblePosition { x: number; y: number }

const BUBBLE_WIDTH = 108;
const BUBBLE_HEIGHT = 42;
const SAFE_MARGIN = 16;
const COMPOSER_CLEARANCE = 112;
const POSITION_STORAGE_KEY = "memoraBubblePosition";
let cleanupActivePanel: (() => void) | null = null;

export class MemoraPanel {
  private readonly action: HTMLButtonElement;
  private readonly status: HTMLElement;
  private readonly content: HTMLElement;
  private readonly bubble: HTMLButtonElement;
  private readonly panel: HTMLElement;
  private readonly minimize: HTMLButtonElement;
  private readonly sortControl: HTMLElement;
  private readonly sortSelect: HTMLSelectElement;
  private readonly memoryButtons = new Map<string, HTMLButtonElement>();
  private readonly usedMemories = new Map<string, string>();
  private currentMemories: MemoryBrief[] = [];
  private position: BubblePosition;
  private expanded = false;
  private interacted = false;
  private dragStart: { pointerX: number; pointerY: number; x: number; y: number } | null = null;
  private dragged = false;

  constructor(onRetrieve: () => void, private readonly onUseMemory: (memory: MemoryBrief) => void) {
    cleanupActivePanel?.();
    document.getElementById("memora-extension-root")?.remove();
    const host = document.createElement("aside");
    host.id = "memora-extension-root";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `${STYLE}
      <button type="button" class="memory-bubble" id="memora-bubble" aria-label="Open Memora" title="Open Memora" aria-controls="memora-panel" aria-expanded="false"><svg aria-hidden="true" viewBox="0 0 16 16"><path d="M3.25 2.75h9.5a1.5 1.5 0 0 1 1.5 1.5v5.5a1.5 1.5 0 0 1-1.5 1.5H8l-3.55 2.2.55-2.2H3.25a1.5 1.5 0 0 1-1.5-1.5v-5.5a1.5 1.5 0 0 1 1.5-1.5Z"/></svg><span>Memora</span></button>
      <section class="panel" id="memora-panel" aria-label="Memora relevant memories" hidden>
        <header><span class="brand-mark" aria-hidden="true"></span><div><strong>Memora</strong><span>Relevant memories</span></div><button type="button" id="memora-minimize" class="minimize" aria-label="Minimize Memora" title="Minimize Memora">&#8722;</button></header>
        <p id="memora-status" role="status" aria-live="polite">Relevant memories for your current question.</p>
        <div class="sort-control" id="memora-sort-control" hidden><label for="memora-sort">Sort</label><select id="memora-sort" aria-label="Sort memories"><option value="best">Best match</option><option value="recent">Most recent</option></select></div>
        <div id="memora-content" class="content"></div>
        <div class="actions"><button type="button" id="memora-retrieve" class="secondary">Retrieve memory</button></div>
      </section>`;
    document.body.append(host);
    this.action = required(root, "#memora-retrieve", HTMLButtonElement);
    this.status = required(root, "#memora-status", HTMLElement);
    this.content = required(root, "#memora-content", HTMLElement);
    this.bubble = required(root, "#memora-bubble", HTMLButtonElement);
    this.panel = required(root, "#memora-panel", HTMLElement);
    this.minimize = required(root, "#memora-minimize", HTMLButtonElement);
    this.sortControl = required(root, "#memora-sort-control", HTMLElement);
    this.sortSelect = required(root, "#memora-sort", HTMLSelectElement);
    this.position = defaultPosition();
    this.applyPosition();
    this.action.addEventListener("click", onRetrieve);
    this.bubble.addEventListener("click", () => {
      if (this.dragged) { this.dragged = false; return; }
      this.setExpanded(!this.expanded);
    });
    this.bubble.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        this.setExpanded(!this.expanded);
      }
    });
    this.minimize.addEventListener("click", () => this.setExpanded(false));
    this.sortSelect.addEventListener("change", () => this.renderCards());
    this.bubble.addEventListener("pointerdown", (event) => this.startDrag(event));
    window.addEventListener("pointermove", this.moveDrag);
    window.addEventListener("pointerup", this.endDrag);
    window.addEventListener("resize", this.handleResize);
    cleanupActivePanel = () => {
      window.removeEventListener("pointermove", this.moveDrag);
      window.removeEventListener("pointerup", this.endDrag);
      window.removeEventListener("resize", this.handleResize);
    };
    void this.restorePosition();
  }

  setDraftAvailable(available: boolean): void { this.action.dataset.draftAvailable = String(available); }
  showIdle(message = "Relevant memories for your current question."): void {
    this.currentMemories = [];
    delete this.bubble.dataset.hasMemories;
    this.action.textContent = "Retrieve memory";
    this.renderState("idle", message);
  }
  showLoading(): void {
    this.currentMemories = [];
    delete this.bubble.dataset.hasMemories;
    this.action.disabled = true;
    this.renderState("loading", "Searching your memory...");
  }
  showError(message: string): void {
    this.currentMemories = [];
    delete this.bubble.dataset.hasMemories;
    this.action.disabled = false;
    this.action.textContent = "Try again";
    this.renderState("error", message);
  }
  showInsertionError(message: string): void {
    this.status.dataset.state = "error";
    this.status.textContent = message;
  }
  showMemoryUsed(threadId: string, alreadyInserted = false): void {
    this.usedMemories.set(threadId, alreadyInserted ? "Already in draft" : "Added to draft");
    const button = this.memoryButtons.get(threadId);
    if (button) {
      button.disabled = true;
      button.textContent = alreadyInserted ? "Already in draft" : "Added to draft";
    }
    this.status.dataset.state = "results";
    this.status.textContent = alreadyInserted
      ? "This memory is already in your draft."
      : "Memory added to your draft. Nothing was submitted.";
  }

  clearMemories(): void {
    this.currentMemories = [];
    this.usedMemories.clear();
    delete this.bubble.dataset.hasMemories;
    this.action.disabled = false;
    this.action.textContent = "Retrieve memory";
    this.renderState("idle", "Memora data cleared. Retrieve after importing memory again.");
  }

  showResults(response: ContextResponse): void {
    this.action.disabled = false;
    this.action.textContent = "Retrieve again";
    if (response.memories.length === 0) {
      this.currentMemories = [];
      delete this.bubble.dataset.hasMemories;
      this.renderState("empty", "No relevant memory found for this question.");
      return;
    }
    const memories = response.memories.slice(0, 5);
    this.currentMemories = memories;
    this.sortSelect.value = "best";
    this.bubble.dataset.hasMemories = "true";
    const partial = memories.some((memory) => memory.used_fallback);
    this.renderState(
      partial ? "partial" : "results",
      partial ? "Relevant memories found. Some details used a local fallback." : "Relevant memories found.",
    );
    this.sortControl.hidden = false;
    this.renderCards();
  }

  private renderCards(): void {
    this.content.replaceChildren();
    this.memoryButtons.clear();
    const indexed = this.currentMemories.map((memory, index) => ({ memory, index }));
    if (this.sortSelect.value === "recent") {
      indexed.sort((left, right) => {
        const rightTime = trustedTime(right.memory.latest_timestamp);
        const leftTime = trustedTime(left.memory.latest_timestamp);
        return rightTime - leftTime || left.index - right.index;
      });
    }
    indexed.forEach(({ memory }, index) => this.content.append(this.createCard(memory, index)));
  }

  private createCard(memory: MemoryBrief, index: number): HTMLElement {
    const card = document.createElement("article");
    card.className = "memory-card";
    const heading = document.createElement("div");
    heading.className = "card-heading";
    const title = document.createElement("strong");
    title.textContent = memory.title || "Relevant memory";
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = index === 0 ? "Top memory" : "Related";
    heading.append(title, badge);
    const summary = document.createElement("p");
    summary.className = "summary";
    summary.textContent = memory.summary;
    const timestampLabel = formatTimestamp(memory.latest_timestamp);
    const timestamp = document.createElement("p");
    timestamp.className = "timestamp";
    timestamp.textContent = timestampLabel ?? "";
    timestamp.hidden = timestampLabel === null;
    const details = document.createElement("div");
    details.className = "details";
    details.hidden = index !== 0;
    if (memory.subject && memory.subject !== "unknown") {
      const subject = document.createElement("p");
      subject.className = "subject";
      subject.textContent = `About: ${formatSubject(memory.subject)}`;
      details.append(subject);
    }
    if (memory.key_details.length) details.append(labelledList("Key details", memory.key_details));
    if (memory.sources.length) details.append(labelledList("Sources", memory.sources.map(formatSource)));
    if (index !== 0) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "link-button";
      toggle.textContent = "View details";
      toggle.addEventListener("click", () => {
        details.hidden = !details.hidden;
        toggle.textContent = details.hidden ? "View details" : "Hide details";
      });
      card.append(heading, timestamp, summary, toggle, details);
    } else card.append(heading, timestamp, summary, details);
    const use = document.createElement("button");
    use.type = "button";
    use.textContent = "Use This Context";
    const usedLabel = this.usedMemories.get(memory.thread_id);
    if (usedLabel) {
      use.disabled = true;
      use.textContent = usedLabel;
    }
    use.addEventListener("click", () => this.onUseMemory(memory));
    this.memoryButtons.set(memory.thread_id, use);
    card.append(use);
    return card;
  }

  private renderState(state: PanelState, message: string): void {
    this.content.replaceChildren();
    this.memoryButtons.clear();
    this.sortControl.hidden = true;
    this.status.dataset.state = state;
    this.status.textContent = message;
  }

  private setExpanded(expanded: boolean): void {
    this.expanded = expanded;
    this.panel.hidden = !expanded;
    this.bubble.setAttribute("aria-expanded", String(expanded));
    this.bubble.setAttribute("aria-label", expanded ? "Memora is open" : "Open Memora");
    if (expanded) this.applyPanelDirection();
  }

  private startDrag(event: PointerEvent): void {
    if (event.button !== 0) return;
    this.interacted = true;
    this.dragged = false;
    this.dragStart = { pointerX: event.clientX, pointerY: event.clientY, ...this.position };
    this.bubble.classList.add("dragging");
  }

  private readonly moveDrag = (event: PointerEvent): void => {
    if (!this.dragStart) return;
    const deltaX = event.clientX - this.dragStart.pointerX;
    const deltaY = event.clientY - this.dragStart.pointerY;
    if (Math.abs(deltaX) + Math.abs(deltaY) > 4) this.dragged = true;
    this.position = clampPosition({
      x: this.dragStart.x + deltaX,
      y: this.dragStart.y + deltaY,
    });
    this.applyPosition();
  };

  private readonly endDrag = (): void => {
    if (!this.dragStart) return;
    this.dragStart = null;
    this.bubble.classList.remove("dragging");
    if (this.dragged) void persistPosition(this.position);
  };

  private readonly handleResize = (): void => {
    this.position = clampPosition(this.position);
    this.applyPosition();
  };

  private applyPosition(): void {
    this.bubble.style.left = `${this.position.x}px`;
    this.bubble.style.top = `${this.position.y}px`;
    if (this.expanded) this.applyPanelDirection();
  }

  private applyPanelDirection(): void {
    const opensLeft = this.position.x + BUBBLE_WIDTH / 2 >= window.innerWidth / 2;
    this.panel.dataset.direction = opensLeft ? "left" : "right";
    this.panel.style.top = `${Math.min(
      Math.max(SAFE_MARGIN, this.position.y - 24),
      Math.max(SAFE_MARGIN, window.innerHeight * 0.2),
    )}px`;
    if (opensLeft) {
      this.panel.style.left = "auto";
      this.panel.style.right = `${Math.max(SAFE_MARGIN, window.innerWidth - this.position.x + 10)}px`;
    } else {
      this.panel.style.right = "auto";
      this.panel.style.left = `${Math.max(SAFE_MARGIN, this.position.x + BUBBLE_WIDTH + 10)}px`;
    }
  }

  private async restorePosition(): Promise<void> {
    const stored = await loadPosition();
    if (!stored || this.interacted) return;
    this.position = clampPosition(stored);
    this.applyPosition();
  }
}

function defaultPosition(): BubblePosition {
  return clampPosition({
    x: window.innerWidth - BUBBLE_WIDTH - SAFE_MARGIN,
    y: Math.round(window.innerHeight * 0.42 - BUBBLE_HEIGHT / 2),
  });
}

function clampPosition(position: BubblePosition): BubblePosition {
  const maximumX = Math.max(SAFE_MARGIN, window.innerWidth - BUBBLE_WIDTH - SAFE_MARGIN);
  const maximumY = Math.max(
    SAFE_MARGIN,
    window.innerHeight - BUBBLE_HEIGHT - COMPOSER_CLEARANCE,
  );
  return {
    x: Math.min(maximumX, Math.max(SAFE_MARGIN, position.x)),
    y: Math.min(maximumY, Math.max(SAFE_MARGIN, position.y)),
  };
}

async function loadPosition(): Promise<BubblePosition | null> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return null;
  try {
    const stored = await chrome.storage.local.get(POSITION_STORAGE_KEY);
    const value: unknown = stored[POSITION_STORAGE_KEY];
    return isPosition(value) ? value : null;
  } catch {
    return null;
  }
}

async function persistPosition(position: BubblePosition): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return;
  try { await chrome.storage.local.set({ [POSITION_STORAGE_KEY]: position }); } catch { /* best effort */ }
}

function isPosition(value: unknown): value is BubblePosition {
  return typeof value === "object" && value !== null &&
    typeof (value as { x?: unknown }).x === "number" &&
    Number.isFinite((value as { x: number }).x) &&
    typeof (value as { y?: unknown }).y === "number" &&
    Number.isFinite((value as { y: number }).y);
}

function labelledList(label: string, values: readonly string[]): HTMLElement {
  const section = document.createElement("section");
  const heading = document.createElement("b");
  heading.textContent = label;
  const list = document.createElement("ul");
  values.forEach((value) => { const item = document.createElement("li"); item.textContent = value; list.append(item); });
  section.append(heading, list);
  return section;
}
function formatSubject(subject: string): string { return subject.charAt(0).toUpperCase() + subject.slice(1); }
function formatSource(source: MemoryBrief["sources"][number]): string {
  if (source.type === "conversation") return `Chat: ${source.conversation_title}`;
  if (source.type === "attachment") return `Attachment: ${source.filename}`;
  const pages = source.page_start === source.page_end ? `p. ${source.page_start}` : `pp. ${source.page_start}-${source.page_end}`;
  return `PDF: ${source.filename} · ${pages}`;
}
function trustedTime(value: string | null | undefined): number {
  if (!value) return Number.NEGATIVE_INFINITY;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}
function formatTimestamp(value: string | null | undefined): string | null {
  const timestamp = trustedTime(value);
  if (!Number.isFinite(timestamp)) return null;
  const ageDays = (Date.now() - timestamp) / 86_400_000;
  if (ageDays >= 0 && ageDays <= 45) return "Updated recently";
  return `Discussed ${new Intl.DateTimeFormat("en", {
    month: "short", year: "numeric", timeZone: "UTC",
  }).format(new Date(timestamp))}`;
}
function required<T extends Element>(root: ShadowRoot, selector: string, type: { new (): T }): T {
  const element = root.querySelector(selector);
  if (!(element instanceof type)) throw new Error(`Missing panel element: ${selector}`);
  return element;
}

const STYLE = `<style>
  :host { all:initial; --bg:#fff; --surface:#f7f7f7; --text:#111; --body:#333; --muted:#666; --subtle:#777; --border:#e5e5e5; --divider:#eaeaea; --danger:#9f3039; --warning:#765715; }
  * { box-sizing:border-box; }
  .memory-bubble { position:fixed; z-index:2147483647; display:flex; align-items:center; justify-content:center; gap:8px; width:108px; height:42px; min-height:0; padding:0 14px; border:1px solid #e5e5e5; border-radius:14px; background:#fff; color:#111; box-shadow:0 2px 8px rgba(0,0,0,.10); cursor:grab; opacity:.95; font:600 14px/1 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; letter-spacing:0; transition:opacity .15s ease,border-color .15s ease,box-shadow .15s ease,background-color .15s ease,transform .15s ease; touch-action:none; user-select:none; }
  .memory-bubble svg { width:15px; height:15px; flex:0 0 auto; fill:none; stroke:currentColor; stroke-width:1.35; stroke-linecap:round; stroke-linejoin:round; }
  .memory-bubble::before { content:""; position:absolute; right:7px; top:7px; width:6px; height:6px; border-radius:50%; background:#5e9b76; opacity:0; box-shadow:0 0 0 2px #fff; }
  .memory-bubble[data-has-memories=true]::before { opacity:1; }
  .memory-bubble[aria-expanded=true] { background:#f7f7f7; border-color:#d4d4d4; }
  .memory-bubble:hover,.memory-bubble:focus-visible { opacity:1; border-color:#d4d4d4; box-shadow:0 4px 12px rgba(0,0,0,.12); transform:translateY(-1px); }
  .memory-bubble:focus-visible,.minimize:focus-visible,button:focus-visible { outline:2px solid #262626; outline-offset:3px; }
  .memory-bubble.dragging { cursor:grabbing; opacity:1; transform:none; transition:none; }
  .panel { position:fixed; z-index:2147483646; width:min(360px,calc(100vw - 84px)); max-height:min(76vh,680px); overflow:auto; padding:16px; border:1px solid var(--border); border-radius:16px; background:var(--bg); color:var(--text); box-shadow:0 8px 30px rgba(0,0,0,.12); font:14px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  .panel[hidden] { display:none; }
  header { display:flex; align-items:center; gap:10px; margin-bottom:12px; padding-bottom:12px; border-bottom:1px solid var(--divider); } header div { display:grid; flex:1; } header strong { font-size:16px; font-weight:600; letter-spacing:-.01em; } header span { color:var(--muted); font-size:12px; }
  .minimize { width:30px; height:30px; min-height:0; padding:0; border:0; border-radius:8px; background:transparent; color:var(--muted); font-size:20px; line-height:1; } .minimize:hover { background:#f5f5f5; color:var(--text); }
  .brand-mark { width:8px; height:8px; border:1.5px solid #333; border-radius:50%; background:transparent; }
  #memora-status { margin:0 0 14px; color:var(--muted); font-size:13px; overflow-wrap:anywhere; } #memora-status[data-state=error]{color:var(--danger)} #memora-status[data-state=empty]{color:var(--warning)}
  .sort-control { display:flex; align-items:center; justify-content:flex-end; gap:8px; margin:-4px 0 12px; color:var(--subtle); font-size:12px; } .sort-control[hidden] { display:none; } .sort-control select { min-height:30px; padding:4px 26px 4px 8px; border:1px solid #dadada; border-radius:8px; background:#fff; color:#222; font:500 12px/1 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; } .sort-control select:focus-visible { outline:2px solid #262626; outline-offset:2px; }
  .content { display:grid; gap:12px; } .memory-card { display:grid; gap:9px; padding:12px; border:1px solid var(--border); border-radius:11px; background:var(--bg); }
  .memory-card:first-child { border-color:#d9d9d9; }
  .card-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; } .card-heading strong { color:var(--text); font-size:14px; font-weight:600; overflow-wrap:anywhere; }
  .badge { flex:0 0 auto; padding:2px 7px; border-radius:7px; background:#f2f2f2; color:#333; font-size:11px; font-weight:600; }
  .summary,.subject { margin:0; color:var(--body); font-size:13px; line-height:1.5; overflow-wrap:anywhere; } .subject { color:var(--muted); font-size:12px; }
  .timestamp { margin:0; color:var(--subtle); font-size:11px; }
  .details { display:grid; gap:8px; padding:9px 0 0; border-top:1px solid var(--divider); color:#555; font-size:12px; } .details[hidden] { display:none; } .details b { color:#555; font-size:12px; font-weight:600; }
  ul { margin:3px 0 0; padding-left:18px; } li { margin:3px 0; overflow-wrap:anywhere; }
  button { width:100%; min-height:38px; border:1px solid #111; border-radius:10px; padding:8px 12px; background:#111; color:#fff; cursor:pointer; font:inherit; font-weight:600; transition:background-color .15s ease,border-color .15s ease; }
  button:not(.memory-bubble):not(.minimize):not(.secondary):not(.link-button):hover { background:#2a2a2a; border-color:#2a2a2a; } button:disabled { opacity:.6; cursor:default; } button.secondary { border-color:#dadada; background:var(--bg); color:var(--text); } button.secondary:hover { border-color:#ccc; background:#f7f7f7; } .actions { margin-top:14px; }
  .link-button { width:auto; min-height:0; justify-self:start; padding:0; border:0; background:transparent; color:#555; font-size:12px; font-weight:500; } .link-button:hover { background:transparent; color:#111; text-decoration:underline; }
  @media(max-width:700px){.panel{width:min(330px,calc(100vw - 76px));max-height:68vh}}
</style>`;
