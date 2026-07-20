import { MemoraApiClient } from "./api/memora-client";
import { renderImportError, renderImportSummary } from "./import-ui";
import { DEFAULT_SETTINGS, loadSettings, saveSettings, type MemoraSettings } from "./settings";
import { MAX_IMPORT_FILES } from "./security";
import { initializePrivacyControls } from "./privacy-controls";

const form = required<HTMLFormElement>("#settings-form");
const backendUrl = required<HTMLInputElement>("#backend-url");
const localToken = required<HTMLInputElement>("#local-token");
const settingsButton = required<HTMLButtonElement>("#settings-submit");
const status = required<HTMLElement>("#status");
const connectionState = required<HTMLElement>("#connection-state");
const connectionLabel = required<HTMLElement>("#connection-label");
const importForm = required<HTMLFormElement>("#import-form");
const importFiles = required<HTMLInputElement>("#import-files");
const importButton = required<HTMLButtonElement>("#import-submit");
const importStatus = required<HTMLElement>("#import-status");
const documentForm = required<HTMLFormElement>("#document-import-form");
const documentFiles = required<HTMLInputElement>("#document-files");
const documentButton = required<HTMLButtonElement>("#document-import-submit");
const documentStatus = required<HTMLElement>("#document-import-status");
const privacyControls = initializePrivacyControls();

void loadSettings().then(async (settings) => {
  backendUrl.value = settings.backendUrl;
  localToken.value = settings.localToken;
  await checkConnection(settings);
  await privacyControls.refresh();
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
        localToken: localToken.value,
        topK: DEFAULT_SETTINGS.topK,
      });
      const settings = await loadSettings();
      backendUrl.value = settings.backendUrl;
      localToken.value = settings.localToken;
      await checkConnection(settings, true);
      await privacyControls.refresh();
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
    if (files.length > MAX_IMPORT_FILES) {
      renderImportError(importStatus, `Select no more than ${MAX_IMPORT_FILES} export files at once.`);
      return;
    }
    importButton.disabled = true;
    importButton.textContent = "Importing...";
    importStatus.className = "importing";
    importStatus.textContent = "Importing and indexing your history. This may take a few minutes.";
    try {
      const settings = await loadSettings();
      const summary = await new MemoraApiClient(settings.backendUrl, settings.localToken).importChatGPTHistory(files);
      renderImportSummary(importStatus, summary);
      importFiles.value = "";
      setConnection("connected");
      await privacyControls.refresh();
    } catch (error) {
      renderImportError(importStatus, friendlyImportError(error));
    } finally {
      importButton.disabled = false;
      importButton.textContent = "Import history";
    }
  })();
});

documentForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void (async () => {
    const files = Array.from(documentFiles.files ?? []);
    if (!files.length) { renderImportError(documentStatus, "Select one or more text-based PDFs first."); return; }
    if (files.length > 5) { renderImportError(documentStatus, "Select no more than 5 PDFs at once."); return; }
    documentButton.disabled = true;
    documentButton.textContent = "Importing...";
    documentStatus.className = "importing";
    documentStatus.textContent = "Extracting and indexing PDF text locally.";
    try {
      const settings = await loadSettings();
      const summary = await new MemoraApiClient(settings.backendUrl, settings.localToken).importDocuments(files);
      documentStatus.replaceChildren();
      documentStatus.className = summary.documents_skipped ? "partial" : "success";
      const headline = document.createElement("strong");
      headline.textContent = summary.documents_skipped ? "PDF import completed with skips" : "PDF import complete";
      const counts = document.createElement("span");
      counts.textContent = `${summary.documents_imported} imported · ${summary.documents_skipped} skipped · ${summary.document_chunks_indexed} chunks indexed`;
      documentStatus.append(headline, counts);
      if (summary.errors.length) {
        const errors = document.createElement("ul");
        summary.errors.slice(0, 5).forEach((message) => { const item = document.createElement("li"); item.textContent = message; errors.append(item); });
        documentStatus.append(errors);
      }
      documentFiles.value = "";
      await privacyControls.refresh();
    } catch (error) {
      renderImportError(documentStatus, friendlyImportError(error));
    } finally {
      documentButton.disabled = false;
      documentButton.textContent = "Import PDFs";
    }
  })();
});

async function checkConnection(settings: MemoraSettings, saved = false): Promise<void> {
  setConnection("checking");
  status.className = "helper";
  status.textContent = saved ? "Settings saved. Checking connection..." : "";
  try {
    await new MemoraApiClient(settings.backendUrl, settings.localToken).health();
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
  return message || "Your ChatGPT history could not be imported. Check the selected export file.";
}

function required<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing popup element: ${selector}`);
  return element;
}
