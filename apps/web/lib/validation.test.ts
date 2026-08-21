import { describe, expect, it } from "vitest";

import { formatConfidenceInterval, formatMetric } from "./validation";
import type { ValidationMetric } from "./validation";

const metric: ValidationMetric = {
  metric: "event_recall",
  status: "AVAILABLE",
  unit: "proportion",
  population: "eligible reference events",
  n: 100,
  value: 0.72,
  numerator: 72,
  denominator: 100,
  confidence_interval: {
    confidence_level: 0.95,
    lower: 0.621,
    upper: 0.797,
    method: "wilson",
  },
  reason: null,
  limitations: [],
};

describe("validation result formatting", () => {
  it("shows unavailable metrics without manufacturing zero", () => {
    expect(formatMetric({ ...metric, status: "NO_DISPONIBLE", value: null, n: 0 })).toBe(
      "NO DISPONIBLE",
    );
  });

  it("marks small samples and preserves N", () => {
    expect(formatMetric({ ...metric, status: "INSUFFICIENT_SAMPLE", n: 12 })).toBe(
      "INSUFFICIENT SAMPLE · N=12",
    );
  });

  it("formats available proportions and uncertainty separately", () => {
    expect(formatMetric(metric)).toBe("72 %");
    expect(formatConfidenceInterval(metric)).toContain("95 %");
    expect(formatConfidenceInterval({ ...metric, confidence_interval: null })).toBe(
      "NO DISPONIBLE",
    );
  });
});
