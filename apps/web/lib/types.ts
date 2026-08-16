export type SourceState = "OPERATIVO" | "DEGRADADO" | "SIN_DATOS" | "ERROR";

export interface SourceHealth {
  source: string;
  state: SourceState;
  last_received_at: string | null;
  latency_seconds: number | null;
  detail: string;
}

export interface SystemStatus {
  generated_at: string;
  mode: "LIVE" | "DEMO";
  sources: SourceHealth[];
}
