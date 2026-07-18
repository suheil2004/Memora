import { MAX_TOP_K, MIN_LOCAL_TOKEN_LENGTH, MIN_TOP_K, isAllowedBackendUrl } from "./security";

export interface MemoraSettings {
  backendUrl: string;
  localToken: string;
  topK: number;
}

export const DEFAULT_SETTINGS: MemoraSettings = {
  backendUrl: "http://127.0.0.1:8765",
  localToken: "",
  topK: 5,
};

export async function loadSettings(): Promise<MemoraSettings> {
  const [stored, secrets] = await Promise.all([
    chrome.storage.sync.get(["backendUrl", "topK"]),
    chrome.storage.local.get(["localToken"]),
  ]);
  const topK = typeof stored.topK === "number" && Number.isInteger(stored.topK) &&
      stored.topK >= MIN_TOP_K && stored.topK <= MAX_TOP_K
    ? stored.topK
    : DEFAULT_SETTINGS.topK;
  return {
    backendUrl: validBackendUrl(stored.backendUrl),
    localToken: typeof secrets.localToken === "string" ? secrets.localToken : "",
    topK,
  };
}

export async function saveSettings(settings: MemoraSettings): Promise<void> {
  const token = settings.localToken.trim();
  if (token.length < MIN_LOCAL_TOKEN_LENGTH) {
    throw new Error(`Memora local token must be at least ${MIN_LOCAL_TOKEN_LENGTH} characters.`);
  }
  if (!Number.isInteger(settings.topK) || settings.topK < MIN_TOP_K || settings.topK > MAX_TOP_K) {
    throw new Error(`Top K must be between ${MIN_TOP_K} and ${MAX_TOP_K}.`);
  }
  await Promise.all([
    chrome.storage.sync.set({
      backendUrl: normalizeBackendUrl(settings.backendUrl),
      topK: settings.topK,
    }),
    chrome.storage.local.set({ localToken: token }),
  ]);
}

export function normalizeBackendUrl(value: string): string {
  const url = new URL(value.trim());
  if (!isAllowedBackendUrl(url.toString())) {
    throw new Error("Backend URL must be http://127.0.0.1:8765 or http://localhost:8765.");
  }
  return url.origin;
}

function validBackendUrl(value: unknown): string {
  if (typeof value !== "string") return DEFAULT_SETTINGS.backendUrl;
  try {
    return normalizeBackendUrl(value);
  } catch {
    return DEFAULT_SETTINGS.backendUrl;
  }
}
