import type { BackgroundRequest, BackgroundResponse } from "./api/types";
import { type BackgroundDependencies, handleBackgroundRequest } from "./background-handler";
import { debug } from "./debug";

export interface BackgroundRuntime {
  onMessage: {
    addListener(
      callback: (
        message: unknown,
        sender: unknown,
        sendResponse: (response: BackgroundResponse) => void,
      ) => boolean,
    ): void;
  };
}

export function registerBackgroundListener(
  runtime: BackgroundRuntime = chrome.runtime,
  dependencies?: BackgroundDependencies,
): void {
  runtime.onMessage.addListener((message, _sender, sendResponse) => {
    debug("BACKGROUND", "message received");
    const messageType = readMessageType(message);
    debug("BACKGROUND", "received message type", messageType ?? "missing");
    if (!isRetrieveRequest(message)) {
      debug("BACKGROUND", "payload validation failed");
      return false;
    }
    debug("BACKGROUND", "payload validation passed");
    void handleBackgroundRequest(message, dependencies).then((response) => {
      debug("BACKGROUND", response.ok ? "API response returned" : "error returned", {
        ok: response.ok,
      });
      sendResponse(response);
    });
    // Required for callback-style asynchronous responses in Manifest V3.
    return true;
  });
  debug("BACKGROUND", "listener registered");
}

export function isRetrieveRequest(value: unknown): value is BackgroundRequest {
  return typeof value === "object" && value !== null &&
    (value as { type?: unknown }).type === "MEMORA_RETRIEVE_CONTEXT" &&
    typeof (value as { query?: unknown }).query === "string";
}

function readMessageType(value: unknown): string | null {
  if (typeof value !== "object" || value === null) return null;
  const type = (value as { type?: unknown }).type;
  return typeof type === "string" ? type : null;
}
