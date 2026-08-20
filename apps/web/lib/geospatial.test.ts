import { describe, expect, it } from "vitest";

import { layerAvailability } from "./geospatial";

describe("geospatial layer status", () => {
  it("does not claim availability without catalogued products", () => {
    expect(layerAvailability([], ["NDVI"])).toBe("NO DISPONIBLE");
  });

  it("keeps partial coverage explicit", () => {
    expect(
      layerAvailability(
        [
          {
            layer: "NDVI",
            availability: "PARTIAL",
            product_count: 1,
            latest_observed_at: "2026-08-19T10:00:00Z",
            finest_resolution_m: 10,
            message: "Cobertura parcial",
          },
        ],
        ["NDVI", "NDMI", "NBR"],
      ),
    ).toBe("PARCIAL");
  });
});
