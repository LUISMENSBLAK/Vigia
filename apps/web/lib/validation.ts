import { API_BASE_URL } from "./geospatial";

export interface ValidationDatasetSummary {
  id: string;
  version: string;
  dataset_hash: string;
  event_count: number;
  control_count: number;
  regions_covered: string[];
  years_covered: number[];
  coverage_limitations: string[];
  selection_policy_version: string;
  frozen: boolean;
  split_id: string | null;
  split_version: string | null;
  split_hash: string | null;
  development_count: number | null;
  validation_count: number | null;
  test_count: number | null;
  test_frozen: boolean | null;
  leakage_checked: boolean | null;
}

export interface ValidationRunSummary {
  id: string;
  run_key: string;
  split_role: "DEVELOPMENT" | "VALIDATION" | "TEST";
  dataset_version: string;
  split_version: string;
  engine_version: string;
  matcher_version: string;
  commit_sha: string;
  report_hash: string;
  published: boolean;
  reproducible: boolean;
  live_state_mutated: false;
}

export interface ValidationMetric {
  metric: string;
  status: "AVAILABLE" | "INSUFFICIENT_SAMPLE" | "NO_DISPONIBLE";
  unit: string;
  population: string;
  n: number;
  value: number | null;
  numerator: number | null;
  denominator: number | null;
  confidence_interval: {
    confidence_level: number;
    lower: number;
    upper: number;
    method: string;
  } | null;
  reason: string | null;
  limitations: string[];
}

export interface ValidationReport {
  report_version: string;
  run_key: string;
  dataset_version: string;
  dataset_hash: string;
  split_version: string;
  split_hash: string;
  split_role: "DEVELOPMENT" | "VALIDATION" | "TEST";
  engine_versions: Record<string, string>;
  matcher_version: string;
  matcher_configuration_hash: string;
  code_commit: string;
  sample_counts: Record<string, number>;
  eligibility_counts: Record<string, number>;
  excluded_counts: Record<string, number>;
  metrics: ValidationMetric[];
  limitations: string[];
  unavailable_metrics: string[];
  test_access_audit_id: string | null;
  live_state_mutated: false;
  report_hash: string;
}

export interface ValidationRunDetail {
  id: string;
  report: ValidationReport;
  report_hash: string;
  published: boolean;
  reproducible: boolean;
  live_state_mutated: false;
}

async function jsonRequest<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`VALIDATION_API_${response.status}`);
  return (await response.json()) as T;
}

export function loadValidationDatasets(signal?: AbortSignal) {
  return jsonRequest<ValidationDatasetSummary[]>("/api/validation/datasets", signal);
}

export function loadValidationRuns(signal?: AbortSignal) {
  return jsonRequest<ValidationRunSummary[]>("/api/validation/runs", signal);
}

export function loadValidationRun(runId: string, signal?: AbortSignal) {
  return jsonRequest<ValidationRunDetail>(
    `/api/validation/runs/${encodeURIComponent(runId)}`,
    signal,
  );
}

export function metricLabel(metric: string): string {
  return metric
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatMetric(metric: ValidationMetric): string {
  if (metric.status === "NO_DISPONIBLE") return "NO DISPONIBLE";
  if (metric.status === "INSUFFICIENT_SAMPLE") return `INSUFFICIENT SAMPLE · N=${metric.n}`;
  if (metric.value === null) return "NO DISPONIBLE";
  if (metric.unit === "proportion") {
    return new Intl.NumberFormat("es-ES", {
      style: "percent",
      maximumFractionDigits: 1,
    }).format(metric.value);
  }
  if (metric.unit === "seconds") {
    return `${new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 }).format(metric.value / 60)} min`;
  }
  if (metric.unit === "metres") {
    return `${new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 }).format(metric.value)} m`;
  }
  return `${new Intl.NumberFormat("es-ES", { maximumFractionDigits: 3 }).format(metric.value)} ${metric.unit}`;
}

export function formatConfidenceInterval(metric: ValidationMetric): string {
  const interval = metric.confidence_interval;
  if (!interval) return "NO DISPONIBLE";
  const percentage = metric.unit === "proportion";
  const format = new Intl.NumberFormat("es-ES", {
    style: percentage ? "percent" : "decimal",
    maximumFractionDigits: percentage ? 1 : 2,
  });
  return `${format.format(interval.lower)} – ${format.format(interval.upper)} (${Math.round(interval.confidence_level * 100)} %)`;
}

