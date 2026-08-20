import { describe, expect, it } from "vitest";

import { geospatialTileUrl, layerAvailability } from "./geospatial";

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

  it("builds an API tile template without embedding credentials", () => {
    const url = geospatialTileUrl("9a3d26dc-0147-4f2e-8309-908f7814e15a");
    expect(url).toContain("/api/geospatial/tiles/9a3d26dc-0147-4f2e-8309-908f7814e15a/{z}/{x}/{y}.png");
    expect(url).not.toContain("token");
  });
});
