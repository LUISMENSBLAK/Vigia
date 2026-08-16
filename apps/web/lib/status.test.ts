import { describe, expect, it } from "vitest";

import { overallState, unavailableStatus } from "./status";

describe("overallState", () => {
  it("never upgrades an unavailable API to operational", () => {
    expect(overallState(unavailableStatus)).toBe("ERROR");
  });
});
