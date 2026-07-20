import { MemoraApiClient, MemoraApiError } from "./api/memora-client";
import type { BackgroundRequest, BackgroundResponse, ExtensionErrorCode } from "./api/types";
import type { MemoraSettings } from "./settings";
import { loadSettings, normalizeBackendUrl } from "./settings";
import { MAX_TOP_K, MIN_LOCAL_TOKEN_LENGTH, MIN_TOP_K } from "./security";
import { debug } from "./debug";

export interface BackgroundDependencies {
  loadSettings: () => Promise<MemoraSettings>;
  createClient: (backendUrl: string, localToken: string) => MemoraApiClient;
  hasHostPermission: (backendUrl: string) => Promise<boolean>;
}

const defaultDependencies: BackgroundDependencies = {
  loadSettings,
  createClient: (backendUrl, localToken) => new MemoraApiClient(backendUrl, localToken),
  hasHostPermission: async (backendUrl) => {
    const url = new URL(backendUrl);
    return chrome.permissions.contains({ origins: [`${url.protocol}//${url.hostname}/*`] });
  },
};

export async function handleBackgroundRequest(
  message: BackgroundRequest,
  dependencies: BackgroundDependencies = defaultDependencies,
): Promise<BackgroundResponse> {
  debug("BACKGROUND", "handler entered");
  try {
    const settings = await dependencies.loadSettings();
    normalizeBackendUrl(settings.backendUrl);
    if (settings.localToken.trim().length < MIN_LOCAL_TOKEN_LENGTH) {
      return failure("INTERNAL_ERROR", "Configure the Memora local token in extension settings.");
    }
    if (!Number.isInteger(settings.topK) || settings.topK < MIN_TOP_K || settings.topK > MAX_TOP_K) {
      return failure("INTERNAL_ERROR", "Memora retrieval settings are invalid.");
    }
    if (!(await dependencies.hasHostPermission(settings.backendUrl))) {
      return failure(
        "CORS_OR_PERMISSION_ERROR",
        "Memora does not have permission to access the configured backend. Reload the extension and check its site access.",
      );
    }
    const client = dependencies.createClient(settings.backendUrl, settings.localToken);
    const statistics = await client.memoryStatistics();
    if (Object.values(statistics).every((count) => count === 0)) {
      return failure(
        "NO_IMPORTED_MEMORY",
        "No memory has been imported into the local Memora service.",
      );
    }
    debug("BACKGROUND", "starting API request", { backendUrl: settings.backendUrl });
    const data = await client.retrieve({
      query: message.query,
      top_k: settings.topK,
    });
    debug("BACKGROUND", "API response received", { resultCount: data.results.length });
    return { ok: true, data };
  } catch (error) {
    if (error instanceof MemoraApiError) {
      debug("BACKGROUND", "error returned", { code: error.code, message: error.message });
      return failure(error.code, error.message);
    }
    debug("BACKGROUND", "error returned", { code: "INTERNAL_ERROR" });
    return failure("INTERNAL_ERROR", "Memora retrieval failed. Try again.");
  }
}

function failure(
  code: ExtensionErrorCode,
  message: string,
): BackgroundResponse {
  return { ok: false, error: { code, message } };
}
