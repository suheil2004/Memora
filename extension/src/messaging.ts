import type { BackgroundRequest, BackgroundResponse, ContextResponse } from "./api/types";
import { debug } from "./debug";

export interface RuntimeMessenger {
  sendMessage(message: BackgroundRequest): Promise<unknown>;
}

export class ExtensionMessagingError extends Error {
  readonly code = "EXTENSION_MESSAGING_ERROR" as const;
}

export async function requestMemoraContext(
  query: string,
  runtime: RuntimeMessenger = chrome.runtime,
): Promise<ContextResponse> {
  const request: BackgroundRequest = { type: "MEMORA_RETRIEVE_CONTEXT", query };
  debug("CONTENT", "sending runtime message", { type: request.type, queryLength: query.length });
  let response: BackgroundResponse | undefined;
  try {
    response = await runtime.sendMessage(request) as BackgroundResponse | undefined;
  } catch {
    debug("CONTENT", "runtime messaging exception");
    throw new ExtensionMessagingError(
      "Memora could not contact its background service. Reload the extension and refresh ChatGPT.",
    );
  }
  debug("CONTENT", "runtime response received", { ok: response?.ok === true });
  if (!response || typeof response.ok !== "boolean") {
    throw new ExtensionMessagingError("Memora received an invalid response from its background service.");
  }
  if (!response.ok) throw new Error(response.error.message);
  return response.data;
}
