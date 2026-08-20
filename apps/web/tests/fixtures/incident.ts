import type { IncidentDetail, IncidentFeature } from "../../lib/types";

export const SYNTHETIC_TEST_DATA_NOTICE = "SYNTHETIC TEST DATA — NEVER USE IN LIVE WEB";

export const syntheticIncident: IncidentFeature = {
  type: "Feature",
  geometry: { type: "Point", coordinates: [0, 0] },
  properties: {
    id: "synthetic-incident",
    code: "VIGIA-SYNTHETIC",
    state: "ANOMALIA",
    first_signal_at: "2026-08-20T12:00:00Z",
    last_observation_at: "2026-08-20T12:10:00Z",
    observation_count: 2,
    source_families: ["NASA_VIIRS"],
    evidence_strength: "MEDIA",
    data_quality: "COMPLETA",
    data_age_seconds: 60,
    stale: false,
  },
};

export const syntheticIncidentDetail: IncidentDetail = {
  id: "synthetic-incident",
  code: "VIGIA-SYNTHETIC",
  state: "ANOMALIA",
  centroid: { type: "Point", coordinates: [0, 0] },
  first_signal_at: "2026-08-20T12:00:00Z",
  last_observation_at: "2026-08-20T12:10:00Z",
  processed_at: "2026-08-20T12:11:00Z",
  observation_count: 2,
  source_families: ["NASA_VIIRS"],
  evidence_strength: "MEDIA",
  reason_codes: ["MULTI_SENSOR_AGREEMENT"],
  explanations: ["2 observaciones térmicas compatibles"],
  missing_information: ["segunda familia térmica aproximadamente independiente"],
  persistence: { detection_count: 2 },
  data_quality: "COMPLETA",
  stale: false,
  rule_version: "detection-rules-v1",
  configuration_hash: "a".repeat(64),
};
