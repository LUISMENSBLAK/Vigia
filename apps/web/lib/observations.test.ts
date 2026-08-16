import { describe, expect, it } from "vitest";

import {
  emptyObservations,
  formatAge,
  observationLabel,
  unavailableObservations,
} from "./observations";
import type { FireObservationFeature } from "./types";

const observation: FireObservationFeature = {
  type: "Feature",
  geometry: { type: "Point", coordinates: [-4.7, 40.65] },
  properties: {
    id: "test-observation",
    source: "NASA FIRMS VIIRS NOAA-20",
    platform: "N20",
    sensor: "VIIRS",
    observed_at: "2026-08-14T07:31:00Z",
    received_at: "2026-08-14T08:00:00Z",
    confidence_raw: "n",
    brightness_kelvin: 331.2,
    frp_mw: 4.8,
    daynight: "D",
    age_seconds: 1740,
    provenance: { transformation: "firms_area_csv_v1" },
  },
};

describe("thermal observation presentation", () => {
  it("keeps empty and unavailable states distinct", () => {
    expect(emptyObservations.metadata.data_state).toBe("SIN_DATOS");
    expect(emptyObservations.metadata.message).toBe("SIN OBSERVACIONES ACTIVAS");
    expect(unavailableObservations.metadata.data_state).toBe("ERROR");
    expect(unavailableObservations.metadata.message).toContain("NO DISPONIBLE");
  });

  it("creates a textual alternative with sensor, UTC time and coordinates", () => {
    const label = observationLabel(observation);
    expect(label).toContain("VIIRS");
    expect(label).toContain("UTC");
    expect(label).toContain("40.6500, -4.7000");
  });

  it("formats observed age without adding precision", () => {
    expect(formatAge(59)).toBe("59 s");
    expect(formatAge(1740)).toBe("29 min");
    expect(formatAge(7200)).toBe("2 h");
  });
});
