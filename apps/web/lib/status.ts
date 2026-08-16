import type { SystemStatus } from "./types";

export const unavailableStatus: SystemStatus = {
  generated_at: "",
  mode: "LIVE",
  sources: [
    {
      source: "API VIGÍA",
      state: "ERROR",
      checked_at: null,
      last_observed_at: null,
      last_received_at: null,
      latency_seconds: null,
      error_code: "API_UNAVAILABLE",
      detail: "No se pudo verificar la API.",
    },
  ],
};

export async function loadSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const response = await fetch(`${apiUrl}/v1/status`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`API status ${response.status}`);
  return (await response.json()) as SystemStatus;
}

export function overallState(status: SystemStatus): "OPERATIVO" | "DEGRADADO" | "SIN_DATOS" | "ERROR" {
  if (status.sources.some((source) => source.state === "ERROR")) return "ERROR";
  if (status.sources.some((source) => source.state === "DEGRADADO")) return "DEGRADADO";
  if (status.sources.every((source) => source.state === "SIN_DATOS")) return "SIN_DATOS";
  if (status.sources.every((source) => source.state === "OPERATIVO")) return "OPERATIVO";
  return "DEGRADADO";
}
