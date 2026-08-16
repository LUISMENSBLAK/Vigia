import type { FireObservationCollection, FireObservationFeature } from "./types";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const emptyObservations: FireObservationCollection = {
  type: "FeatureCollection",
  features: [],
  metadata: {
    data_state: "SIN_DATOS",
    message: "SIN OBSERVACIONES ACTIVAS",
    count: 0,
    generated_at: "",
  },
};

export const unavailableObservations: FireObservationCollection = {
  type: "FeatureCollection",
  features: [],
  metadata: {
    data_state: "ERROR",
    message: "NO DISPONIBLE: no se pudo consultar la API VIGÍA.",
    count: 0,
    generated_at: "",
  },
};

export async function loadFireObservations(
  signal?: AbortSignal,
): Promise<FireObservationCollection> {
  const response = await fetch(`${apiUrl}/v1/fire-observations`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`API observations ${response.status}`);
  return (await response.json()) as FireObservationCollection;
}

export function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h`;
  return `${Math.floor(seconds / 86400)} d`;
}

export function observationLabel(observation: FireObservationFeature): string {
  const timestamp = new Intl.DateTimeFormat("es-ES", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(observation.properties.observed_at));
  return `${observation.properties.sensor} · ${timestamp} UTC · ${observation.geometry.coordinates[1].toFixed(4)}, ${observation.geometry.coordinates[0].toFixed(4)}`;
}
