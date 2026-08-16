import { describe, expect, it } from "vitest";

import { overallState, unavailableStatus } from "./status";

describe("overallState", () => {
  it("never upgrades an unavailable API to operational", () => {
    expect(overallState(unavailableStatus)).toBe("ERROR");
  });

  it("does not call a partially verified system operational", () => {
    expect(overallState({
      generated_at: "2026-08-16T12:00:00Z",
      mode: "LIVE",
      sources: [
        {
          source: "Supabase / PostGIS",
          state: "OPERATIVO",
          checked_at: "2026-08-16T12:00:00Z",
          last_observed_at: null,
          last_received_at: null,
          latency_seconds: null,
          error_code: null,
          detail: "PostGIS verificado.",
        },
        {
          source: "NASA FIRMS",
          state: "SIN_DATOS",
          checked_at: null,
          last_observed_at: null,
          last_received_at: null,
          latency_seconds: null,
          error_code: null,
          detail: "Sin ingestión.",
        },
      ],
    })).toBe("DEGRADADO");
  });
});
