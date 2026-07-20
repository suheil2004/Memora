import { ExtensionMessagingError, MemoraRequestError } from "./messaging";

export function friendlyRetrievalError(error: unknown): string {
  if (error instanceof ExtensionMessagingError) {
    return "Memora needs to be reloaded. Reload the extension, refresh ChatGPT, and try again.";
  }
  if (error instanceof MemoraRequestError) {
    switch (error.code) {
      case "BACKEND_UNREACHABLE":
        return "Memora is offline. Start the local Memora service and try again.";
      case "CORS_OR_PERMISSION_ERROR":
        return "Memora cannot access the local service. Reload the extension and check its site access.";
      case "AUTHENTICATION_FAILED":
        return "Authentication failed. Open Memora settings and make sure the extension token matches the local service.";
      case "NO_IMPORTED_MEMORY":
        return "No memory imported yet. Open Memora settings and import your ChatGPT history first.";
      case "CONFIGURATION_UNAVAILABLE":
        return "Memora is not ready. Open settings and check the local provider configuration.";
      case "REQUEST_TIMEOUT":
        return "Memora is taking longer than expected. Try again; the local service may still be finishing the request.";
      case "INVALID_RESPONSE":
      case "HTTP_ERROR":
      case "INTERNAL_ERROR":
        return "Memora could not prepare memory. Check the local service and try again.";
      case "EXTENSION_MESSAGING_ERROR":
        return "Memora needs to be reloaded. Reload the extension, refresh ChatGPT, and try again.";
    }
  }
  return "Memora could not prepare memory. Check the local service and try again.";
}
