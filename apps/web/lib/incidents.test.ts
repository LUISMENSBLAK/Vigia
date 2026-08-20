import { describe, expect, it } from "vitest";

import { syntheticIncident } from "../tests/fixtures/incident";
import { emptyIncidents, incidentLabel, unavailableIncidents } from "./incidents";

describe("incident presentation", () => {
  it("keeps no-data and API-error states distinct", () => {
    expect(emptyIncidents.metadata.data_state).toBe("SIN_DATOS");
    expect(unavailableIncidents.metadata.data_state).toBe("ERROR");
  });

  it("labels a derived incident without inventing probability", () => {
    const label = incidentLabel(syntheticIncident);
    expect(label).toContain("ANOMALIA");
    expect(label).toContain("UTC");
    expect(label).not.toContain("%");
  });
});
