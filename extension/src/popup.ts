import { DEFAULT_SETTINGS, loadSettings, saveSettings } from "./settings";

const form = document.querySelector<HTMLFormElement>("#settings-form");
const backendUrl = document.querySelector<HTMLInputElement>("#backend-url");
const userId = document.querySelector<HTMLInputElement>("#user-id");
const status = document.querySelector<HTMLElement>("#status");
if (!form || !backendUrl || !userId || !status) throw new Error("Settings UI is incomplete.");

void loadSettings().then((settings) => {
  backendUrl.value = settings.backendUrl;
  userId.value = settings.userId;
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void (async () => {
    try {
      await saveSettings({
        backendUrl: backendUrl.value || DEFAULT_SETTINGS.backendUrl,
        userId: userId.value || DEFAULT_SETTINGS.userId,
        topK: DEFAULT_SETTINGS.topK,
      });
      status.textContent = "Settings saved.";
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : "Unable to save settings.";
    }
  })();
});
