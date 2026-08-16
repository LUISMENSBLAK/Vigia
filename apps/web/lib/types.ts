export type SourceState = "OPERATIVO" | "DEGRADADO" | "SIN_DATOS" | "ERROR";

export interface SourceHealth {
  source: string;
  state: SourceState;
  checked_at: string | null;
  last_observed_at: string | null;
  last_received_at: string | null;
  latency_seconds: number | null;
  error_code: string | null;
  detail: string;
}

export interface SystemStatus {
  generated_at: string;
  mode: "LIVE" | "DEMO";
  sources: SourceHealth[];
}

export interface FireObservationProperties {
  id: string;
  source: string;
  satellite: string;
  sensor: string;
  observed_at: string;
  received_at: string;
  confidence_raw: string | null;
  brightness_kelvin: number | null;
  frp_mw: number | null;
  daynight: string | null;
  age_seconds: number;
  provenance: Record<string, unknown> | null;
}

export interface FireObservationFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: FireObservationProperties;
}

export interface FireObservationCollection {
  type: "FeatureCollection";
  features: FireObservationFeature[];
  metadata: {
    data_state: SourceState;
    message: string;
    count: number;
    generated_at: string;
  };
}
