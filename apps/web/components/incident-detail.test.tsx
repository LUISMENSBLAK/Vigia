import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  SYNTHETIC_TEST_DATA_NOTICE,
  syntheticIncident,
  syntheticIncidentDetail,
} from "../tests/fixtures/incident";
import { IncidentDetailPanel } from "./incident-detail";

describe("accessible incident explanation", () => {
  it("renders structured reasons and missing information without probability", () => {
    expect(SYNTHETIC_TEST_DATA_NOTICE).toContain("SYNTHETIC TEST DATA");
    const { container } = render(
      <IncidentDetailPanel incident={syntheticIncident} detail={syntheticIncidentDetail} />,
    );
    expect(screen.getByRole("heading", { name: "¿Por qué este estado?" })).toBeVisible();
    expect(screen.getByText("2 observaciones térmicas compatibles")).toBeVisible();
    expect(
      screen.getByText("segunda familia térmica aproximadamente independiente"),
    ).toBeVisible();
    expect(container.textContent).not.toContain("%");
    expect(container.textContent).not.toContain("probabilidad");
  });
});
