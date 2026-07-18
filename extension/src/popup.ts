import { MemoraApiClient } from "./api/memora-client";
import { renderImportError, renderImportSummary } from "./import-ui";
import { DEFAULT_SETTINGS, loadSettings, saveSettings, type MemoraSettings } from "./settings";

const form = required<HTMLFormElement>("#settings-form");
const backendUrl = required<HTMLInputElement>("#backend-url");
const userId = required<HTMLInputElement>("#user-id");
const settingsButton = required<HTMLButtonElement>("#settings-submit");
const status = required<HTMLElement>("#status");
const connectionState = required<HTMLElement>("#connection-state");
const connectionLabel = required<HTMLElement>("#connection-label");
const importForm = required<HTMLFormElement>("#import-form");
const importFiles = required<HTMLInputElement>("#import-files");
const importButton = required<HTMLButtonElement>("#import-submit");
const importStatus = required<HTMLElement>("#import-status");

void loadSettings().then(async (settings) => {
  backendUrl.value = settings.backendUrl;
  userId.value = settings.userId;
  await checkConnection(settings);
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void (async () => {
    settingsButton.disabled = true;
    settingsButton.textContent = "Saving...";
    status.className = "helper";
    status.textContent = "";
    try {
      await saveSettings({
        backendUrl: backendUrl.value || DEFAULT_SETTINGS.backendUrl,
        userId: userId.value || DEFAULT_SETTINGS.userId,
        topK: DEFAULT_SETTINGS.topK,
      });
      const settings = await loadSettings();
      backendUrl.value = settings.backendUrl;
      userId.value = settings.userId;
      await checkConnection(settings, true);
    } catch {
      setConnection("offline");
      status.className = "helper error";
      status.textContent = "Couldn't save settings. Check the backend URL and try again.";
    } finally {
      settingsButton.disabled = false;
      settingsButton.textContent = "Save settings";
    }
  })();
});

importForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void (async () => {
    const files = Array.from(importFiles.files ?? []);
    if (files.length === 0) {
      renderImportError(importStatus, "Select a ChatGPT JSON or ZIP export first.");
      return;
    }
    importButton.disabled = true;
    importButton.textContent = "Importing...";
    importStatus.className = "importing";
    importStatus.textContent = "Importing and indexing your history. This may take a few minutes.";
    try {
      const settings = await loadSettings();
      const summary = await new MemoraApiClient(settings.backendUrl).importChatGPTHistory(files, settings.userId);
      renderImportSummary(importStatus, summary);
      importFiles.value = "";
      setConnection("connected");
    } catch (error) {
      renderImportError(importStatus, friendlyImportError(error));
    } finally {
      importButton.disabled = false;
      importButton.textContent = "Import history";
    }
  })();
});

async function checkConnection(settings: MemoraSettings, saved = false): Promise<void> {
  setConnection("checking");
  status.className = "helper";
  status.textContent = saved ? "Settings saved. Checking connection..." : "";
  try {
    await new MemoraApiClient(settings.backendUrl).health();
    setConnection("connected");
    status.textContent = saved ? "Settings saved. Memora is ready." : "";
  } catch {
    setConnection("offline");
    status.className = "helper error";
    status.textContent = "Memora backend is offline. Start the local service to use retrieval and imports.";
  }
}

function setConnection(state: "checking" | "connected" | "offline"): void {
  connectionState.className = `status-pill ${state}`;
  connectionLabel.textContent = state === "connected" ? "Connected" : state === "offline" ? "Offline" : "Checking...";
}

function friendlyImportError(error: unknown): string {
  const message = error instanceof Error ? error.message : "";
  if (/backend|reach|network|fetch/i.test(message)) {
    setConnection("offline");
    return "Memora backend is offline. Start the local service and try again.";
  }
  return message || "Couldn't import this export. Check the file and try again.";
}

function required<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing popup element: ${selector}`);
  return element;
}
