import { MemoraApiClient } from "./api/memora-client";
import type { BackgroundRequest, BackgroundResponse } from "./api/types";
import { loadSettings } from "./settings";

chrome.runtime.onMessage.addListener(
  (message: unknown, _sender, sendResponse: (response: BackgroundResponse) => void) => {
    if (!isRetrieveRequest(message)) return false;
    void retrieve(message.query).then(sendResponse);
    return true;
  },
);

async function retrieve(query: string): Promise<BackgroundResponse> {
  try {
    const settings = await loadSettings();
    const data = await new MemoraApiClient(settings.backendUrl).retrieve({
      user_id: settings.userId,
      query,
      top_k: settings.topK,
    });
    return { ok: true, data };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "Memora retrieval failed." };
  }
}

function isRetrieveRequest(value: unknown): value is BackgroundRequest {
  return typeof value === "object" && value !== null &&
    (value as { type?: unknown }).type === "MEMORA_RETRIEVE" &&
    typeof (value as { query?: unknown }).query === "string";
}
