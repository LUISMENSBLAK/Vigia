import type { IncidentCollection, IncidentDetail, IncidentFeature } from "./types";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const emptyIncidents: IncidentCollection = {
  type: "FeatureCollection",
  features: [],
  metadata: {
    data_state: "SIN_DATOS",
    message: "SIN INCIDENTES DERIVADOS",
    count: 0,
    generated_at: "",
  },
};

export const unavailableIncidents: IncidentCollection = {
  type: "FeatureCollection",
  features: [],
  metadata: {
    data_state: "ERROR",
    message: "NO DISPONIBLE: no se pudo consultar la API de incidentes.",
    count: 0,
    generated_at: "",
  },
};

export async function loadIncidents(signal?: AbortSignal): Promise<IncidentCollection> {
  const response = await fetch(`${apiUrl}/api/incidents`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`API incidents ${response.status}`);
  return (await response.json()) as IncidentCollection;
}

export async function loadIncidentDetail(
  incidentId: string,
  signal?: AbortSignal,
): Promise<IncidentDetail> {
  const response = await fetch(`${apiUrl}/api/incidents/${incidentId}`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`API incident ${response.status}`);
  return (await response.json()) as IncidentDetail;
}

export function incidentLabel(incident: IncidentFeature): string {
  const timestamp = new Intl.DateTimeFormat("es-ES", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(incident.properties.last_observation_at));
  return `${incident.properties.code} · ${incident.properties.state.replaceAll("_", " ")} · ${timestamp} UTC`;
}
