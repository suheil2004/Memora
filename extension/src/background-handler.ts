import { MemoraApiClient, MemoraApiError } from "./api/memora-client";
import type { BackgroundRequest, BackgroundResponse, ExtensionErrorCode } from "./api/types";
import type { MemoraSettings } from "./settings";
import { loadSettings } from "./settings";
import { debug } from "./debug";

export interface BackgroundDependencies {
  loadSettings: () => Promise<MemoraSettings>;
  createClient: (backendUrl: string) => MemoraApiClient;
  hasHostPermission: (backendUrl: string) => Promise<boolean>;
}

const defaultDependencies: BackgroundDependencies = {
  loadSettings,
  createClient: (backendUrl) => new MemoraApiClient(backendUrl),
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
    if (!(await dependencies.hasHostPermission(settings.backendUrl))) {
      return failure(
        "CORS_OR_PERMISSION_ERROR",
        "Memora does not have permission to access the configured backend. Reload the extension and check its site access.",
      );
    }
    debug("BACKGROUND", "starting API request", { backendUrl: settings.backendUrl });
    const data = await dependencies.createClient(settings.backendUrl).retrieve({
      user_id: settings.userId,
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
