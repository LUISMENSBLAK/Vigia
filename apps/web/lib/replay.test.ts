import { afterEach, describe, expect, it, vi } from "vitest";

import { loadReplayCases, loadReplayObservations, replayStepLabel } from "./replay";
import type { ReplayStep } from "./replay";

afterEach(() => vi.restoreAllMocks());

describe("replay API", () => {
  it("preserves an empty corpus instead of inventing cases", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    await expect(loadReplayCases()).resolves.toEqual([]);
  });

  it("labels the injected replay instant, never the wall clock", () => {
    const step = {
      step_index: 0,
      as_of: "2025-08-16T14:20:00Z",
      visible_input_count: 0,
      visible_observation_count: 0,
      candidate_count: 0,
      incidents: [],
      risk: {},
      availability: {},
      exclusion_counts: {},
      output_hash: "a".repeat(64),
    } satisfies ReplayStep;
    expect(replayStepLabel(step)).toContain("16 ago 2025");
    expect(replayStepLabel(undefined)).toBe("SIN EJECUCIÓN");
  });

  it("requests observations at the selected historical cutoff", async () => {
    const mockedFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ type: "FeatureCollection", features: [], count: 0 }),
    });
    vi.stubGlobal("fetch", mockedFetch);
    await loadReplayObservations("run-id", "2022-07-17T21:30:00Z");
    expect(String(mockedFetch.mock.calls[0]?.[0])).toContain(
      "as_of=2022-07-17T21%3A30%3A00Z",
    );
  });
});
