import { describe, expect, it } from "vitest";

import { MemoraRequestError } from "../src/messaging";
import { friendlyRetrievalError } from "../src/retrieval-errors";

describe("retrieval error guidance", () => {
  it.each([
    ["BACKEND_UNREACHABLE", "offline"],
    ["AUTHENTICATION_FAILED", "Authentication failed"],
    ["NO_IMPORTED_MEMORY", "No memory imported yet"],
    ["CONFIGURATION_UNAVAILABLE", "provider configuration"],
    ["REQUEST_TIMEOUT", "longer than expected"],
    ["HTTP_ERROR", "could not prepare memory"],
  ] as const)("maps %s to actionable copy", (code, expected) => {
    expect(friendlyRetrievalError(new MemoraRequestError(code, "private detail"))).toContain(expected);
  });
});
