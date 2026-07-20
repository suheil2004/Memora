import { MemoraApiError } from "./api/memora-client";
import type { MemoryStatistics } from "./api/types";

export type ReadinessState =
  | "ready"
  | "empty"
  | "offline"
  | "authentication"
  | "unavailable";

export interface ReadinessResult {
  state: ReadinessState;
  label: string;
  message: string;
  statistics?: MemoryStatistics;
}

export async function checkAuthenticatedReadiness(
  client: { memoryStatistics(): Promise<MemoryStatistics> },
): Promise<ReadinessResult> {
  try {
    const statistics = await client.memoryStatistics();
    const storedRecords = Object.values(statistics).reduce((sum, count) => sum + count, 0);
    return storedRecords === 0
      ? {
        state: "empty",
        label: "No memory imported yet",
        message: "Connected — no memory imported yet. Import your ChatGPT history to begin.",
        statistics,
      }
      : {
        state: "ready",
        label: "Ready",
        message: "Memora is connected and memory is available.",
        statistics,
      };
  } catch (error) {
    if (error instanceof MemoraApiError) {
      if (error.code === "AUTHENTICATION_FAILED") {
        return {
          state: "authentication",
          label: "Authentication failed",
          message: "Your extension token does not match the local Memora service.",
        };
      }
      if (error.code === "BACKEND_UNREACHABLE" ||
          error.code === "CORS_OR_PERMISSION_ERROR" ||
          error.code === "REQUEST_TIMEOUT") {
        return {
          state: "offline",
          label: "Memora is offline",
          message: "Start the local Memora service, then check the connection again.",
        };
      }
    }
    return {
      state: "unavailable",
      label: "Configuration unavailable",
      message: "Memora is running but not ready. Check the local provider configuration.",
    };
  }
}
