import { API_BASE_URL } from "./geospatial";

export interface ReplayCaseSummary {
  id: string;
  case_key: string;
  kind: "POSITIVE_REFERENCE" | "CONTROL_NO_KNOWN_FIRE";
  replay_start: string;
  replay_end: string;
  time_step_minutes: number;
  case_version: string;
  reference_quality: string;
  available_sources: string[];
  reference_sources: string[];
  sensor_availability: Record<string, string>;
  manifest_hash: string;
  historical_event_code: string | null;
  name: string | null;
  region: string | null;
  provinces: string[];
  municipality: string | null;
  official_start_time: string | null;
  reference_longitude: number | null;
  reference_latitude: number | null;
  input_count: number;
}

export interface ReplayCaseDetail {
  reference_perimeters: Array<Record<string, unknown>>;
}

export interface ReplayIncident {
  replay_incident_id: string;
  state: string;
  centroid: [number, number];
  first_observation_at: string;
  last_observation_at: string;
  observation_count: number;
  source_families: string[];
  reason_codes: string[];
}

export interface ReplayStep {
  step_index: number;
  as_of: string;
  visible_input_count: number;
  visible_observation_count: number;
  candidate_count: number;
  incidents: ReplayIncident[];
  risk: {
    availability?: string;
    experimental_index?: number | null;
    risk_class?: string;
    data_quality?: string;
    reason_codes?: string[];
  };
  availability: Record<string, string>;
  exclusion_counts: Record<string, number>;
  output_hash: string;
}

export interface ReplayRun {
  id: string;
  run_hash: string;
  state: string;
  code_commit: string;
  step_count: number;
  completed_step: number;
  observations_processed: number;
  wall_time_ms: number | null;
  deterministic: boolean;
  live_state_mutated: false;
  case_id: string;
  case_key: string;
}

export interface ReplayObservationCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: "Point"; coordinates: [number, number] };
    properties: {
      id: string;
      source: string;
      observed_at: string;
      available_at: string;
      platform: string;
      sensor: string;
      confidence_raw: string | null;
      frp_mw: number | null;
      availability_basis: string;
      quality_flags: string[];
    };
  }>;
  as_of: string;
  count: number;
  message: string;
}

export const emptyReplayObservations: ReplayObservationCollection = {
  type: "FeatureCollection",
  features: [],
  as_of: new Date(0).toISOString(),
  count: 0,
  message: "SIN DATOS",
};

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) throw new Error(`REPLAY_API_${response.status}`);
  return (await response.json()) as T;
}

export function loadReplayCases(signal?: AbortSignal): Promise<ReplayCaseSummary[]> {
  return jsonRequest<ReplayCaseSummary[]>("/api/replay/cases", { signal });
}

export function loadReplayCase(
  caseId: string,
  signal?: AbortSignal,
): Promise<ReplayCaseDetail> {
  return jsonRequest<ReplayCaseDetail>(`/api/replay/cases/${encodeURIComponent(caseId)}`, {
    signal,
  });
}

export function createReplayRun(caseId: string): Promise<ReplayRun> {
  return jsonRequest<ReplayRun>("/api/replay/runs", {
    method: "POST",
    body: JSON.stringify({ case_id: caseId }),
  });
}

export function loadReplayTimeline(runId: string): Promise<ReplayStep[]> {
  return jsonRequest<ReplayStep[]>(`/api/replay/runs/${encodeURIComponent(runId)}/timeline`);
}

export function loadReplayObservations(
  runId: string,
  asOf: string,
  signal?: AbortSignal,
): Promise<ReplayObservationCollection> {
  const query = new URLSearchParams({ as_of: asOf, limit: "5000" });
  return jsonRequest<ReplayObservationCollection>(
    `/api/replay/runs/${encodeURIComponent(runId)}/observations?${query}`,
    { signal },
  );
}

export function replayStepLabel(step: ReplayStep | undefined): string {
  if (!step) return "SIN EJECUCIÓN";
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Madrid",
  }).format(new Date(step.as_of));
}
