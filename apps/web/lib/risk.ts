import { API_BASE_URL } from "./geospatial";

export interface RiskAssessment {
  id: string;
  mode: "ANALYSIS" | "FORECAST";
  as_of: string;
  valid_at: string;
  horizon_hours: number;
  experimental_index: number | null;
  risk_class: string;
  data_quality: "COMPLETE" | "PARTIAL" | "INSUFFICIENT_DATA";
  component_scores: Record<string, number | null>;
  component_details: Record<string, unknown>;
  reason_codes: string[];
  explanations: string[];
  missing_components: string[];
  input_resolutions: Record<string, unknown>;
  engine_version: string;
  disclaimer: string;
}

export interface RiskContext {
  availability: "AVAILABLE" | "PARTIAL" | "STALE" | "UNAVAILABLE" | "ERROR";
  longitude: number;
  latitude: number;
  requested_as_of: string;
  assessment: RiskAssessment | null;
  message: string;
}

export interface RiskForecast {
  availability: RiskContext["availability"];
  longitude: number;
  latitude: number;
  requested_as_of: string;
  forecasts: RiskAssessment[];
  message: string;
}

export async function loadRiskContext(
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
): Promise<RiskContext> {
  const query = new URLSearchParams({ lat: String(latitude), lon: String(longitude) });
  const response = await fetch(`${API_BASE_URL}/api/risk/context?${query}`, {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("RISK_CONTEXT_UNAVAILABLE");
  return (await response.json()) as RiskContext;
}

export async function loadRiskForecast(
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
): Promise<RiskForecast> {
  const query = new URLSearchParams({
    lat: String(latitude),
    lon: String(longitude),
    max_horizon_hours: "72",
  });
  const response = await fetch(`${API_BASE_URL}/api/risk/forecast?${query}`, {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("RISK_FORECAST_UNAVAILABLE");
  return (await response.json()) as RiskForecast;
}
