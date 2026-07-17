export interface MemoraSettings {
  backendUrl: string;
  userId: string;
  topK: number;
}

export const DEFAULT_SETTINGS: MemoraSettings = {
  backendUrl: "http://127.0.0.1:8765",
  userId: "demo-user",
  topK: 5,
};

export async function loadSettings(): Promise<MemoraSettings> {
  const stored = await chrome.storage.sync.get(["backendUrl", "userId", "topK"]);
  const userId = typeof stored.userId === "string" ? stored.userId.trim() : "";
  const topK = typeof stored.topK === "number" && Number.isInteger(stored.topK) && stored.topK > 0
    ? stored.topK
    : DEFAULT_SETTINGS.topK;
  return {
    backendUrl: validBackendUrl(stored.backendUrl),
    userId: userId || DEFAULT_SETTINGS.userId,
    topK,
  };
}

export async function saveSettings(settings: MemoraSettings): Promise<void> {
  await chrome.storage.sync.set({
    backendUrl: normalizeBackendUrl(settings.backendUrl),
    userId: settings.userId.trim(),
    topK: settings.topK,
  });
}

export function normalizeBackendUrl(value: string): string {
  const url = new URL(value.trim());
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("Backend URL must use http or https.");
  }
  return url.toString().replace(/\/$/, "");
}

function validBackendUrl(value: unknown): string {
  if (typeof value !== "string") return DEFAULT_SETTINGS.backendUrl;
  try {
    return normalizeBackendUrl(value);
  } catch {
    return DEFAULT_SETTINGS.backendUrl;
  }
}
