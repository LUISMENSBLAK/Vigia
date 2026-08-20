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
  platform: string;
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
    data_state: SourceState | "EXPERIMENTAL";
    message: string;
    count: number;
    generated_at: string;
  };
}

export type IncidentState =
  | "VIGILANCIA"
  | "ANOMALIA"
  | "POSIBLE_IGNICION"
  | "PROBABLE_INCENDIO"
  | "INCENDIO_CONFIRMADO"
  | "DESCARTADO";

export interface IncidentProperties {
  id: string;
  code: string;
  state: IncidentState;
  first_signal_at: string;
  last_observation_at: string;
  observation_count: number;
  source_families: string[];
  evidence_strength: "MUY_BAJA" | "BAJA" | "MEDIA" | "ALTA" | "MUY_ALTA" | null;
  data_quality: "COMPLETA" | "PARCIAL" | "DEGRADADA" | "DESCONOCIDA";
  data_age_seconds: number;
  stale: boolean;
}

export interface IncidentFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: IncidentProperties;
}

export interface IncidentCollection {
  type: "FeatureCollection";
  features: IncidentFeature[];
  metadata: {
    data_state: SourceState;
    message: string;
    count: number;
    generated_at: string;
  };
}

export interface IncidentDetail {
  id: string;
  code: string;
  state: IncidentState;
  centroid: { type: "Point"; coordinates: [number, number] };
  first_signal_at: string;
  last_observation_at: string;
  processed_at: string | null;
  observation_count: number;
  source_families: string[];
  evidence_strength: string | null;
  reason_codes: string[];
  explanations: string[];
  missing_information: string[];
  persistence: Record<string, unknown>;
  data_quality: string;
  stale: boolean;
  rule_version: string | null;
  configuration_hash: string | null;
}

export type GeospatialAvailability =
  | "AVAILABLE"
  | "PARTIAL"
  | "STALE"
  | "UNAVAILABLE"
  | "PROCESSING"
  | "ERROR";

export interface GeospatialLayerStatus {
  layer: string;
  availability: GeospatialAvailability;
  product_count: number;
  latest_observed_at: string | null;
  finest_resolution_m: number | null;
  message: string;
}

export interface GeospatialCoverageProperties {
  id: string;
  product_id: string;
  layer: string;
  availability: GeospatialAvailability;
  observed_at: string | null;
  processed_at: string;
  output_resolution_m: number | null;
  source: string;
  quality: Record<string, unknown>;
  is_experimental: boolean;
  raster_band: number | null;
  value_units: string | null;
  render_hint: Record<string, unknown>;
}

export interface GeospatialCoverageFeature {
  type: "Feature";
  geometry: GeoJSON.Geometry;
  properties: GeospatialCoverageProperties;
}

export interface GeospatialCoverageCollection {
  type: "FeatureCollection";
  features: GeospatialCoverageFeature[];
  as_of: string;
}
