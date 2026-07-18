import { DEFAULT_SETTINGS, loadSettings, saveSettings } from "./settings";
import { MemoraApiClient } from "./api/memora-client";
import { renderImportError, renderImportSummary } from "./import-ui";

const form = document.querySelector<HTMLFormElement>("#settings-form");
const backendUrl = document.querySelector<HTMLInputElement>("#backend-url");
const userId = document.querySelector<HTMLInputElement>("#user-id");
const status = document.querySelector<HTMLElement>("#status");
const importForm = document.querySelector<HTMLFormElement>("#import-form");
const importFiles = document.querySelector<HTMLInputElement>("#import-files");
const importButton = document.querySelector<HTMLButtonElement>("#import-submit");
const importStatus = document.querySelector<HTMLElement>("#import-status");
if (!form || !backendUrl || !userId || !status || !importForm || !importFiles || !importButton || !importStatus) {
  throw new Error("Settings UI is incomplete.");
}

void loadSettings().then((settings) => {
  backendUrl.value = settings.backendUrl;
  userId.value = settings.userId;
});

importForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void (async () => {
    const files = Array.from(importFiles.files ?? []);
    if (files.length === 0) {
      renderImportError(importStatus, "Select one or more ChatGPT JSON/ZIP export files.");
      return;
    }
    importButton.disabled = true;
    importStatus.textContent = "Importing and indexing history. Large exports may take several minutes...";
    try {
      const settings = await loadSettings();
      const summary = await new MemoraApiClient(settings.backendUrl).importChatGPTHistory(
        files,
        settings.userId,
      );
      renderImportSummary(importStatus, summary);
      importFiles.value = "";
    } catch (error) {
      renderImportError(
        importStatus,
        error instanceof Error ? error.message : "Unable to import ChatGPT history.",
      );
    } finally {
      importButton.disabled = false;
    }
  })();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void (async () => {
    try {
      const settings = {
        backendUrl: backendUrl.value || DEFAULT_SETTINGS.backendUrl,
        userId: userId.value || DEFAULT_SETTINGS.userId,
        topK: DEFAULT_SETTINGS.topK,
      };
      await saveSettings(settings);
      status.textContent = "Testing local backend access…";
      await new MemoraApiClient(settings.backendUrl).health();
      status.textContent = "Settings saved. Backend connected.";
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : "Unable to save settings.";
    }
  })();
});
