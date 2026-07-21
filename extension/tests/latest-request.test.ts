import { describe, expect, it } from "vitest";

import { LatestRequestGuard } from "../src/latest-request";

describe("LatestRequestGuard", () => {
  it("prevents an older delayed response from replacing a newer request", () => {
    const guard = new LatestRequestGuard();
    const older = guard.begin();
    const newer = guard.begin();

    expect(guard.isCurrent(older)).toBe(false);
    expect(guard.isCurrent(newer)).toBe(true);
  });

  it("invalidates an in-flight request when results are cleared", () => {
    const guard = new LatestRequestGuard();
    const request = guard.begin();
    guard.invalidate();
    expect(guard.isCurrent(request)).toBe(false);
  });
});
