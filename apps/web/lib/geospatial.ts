import type { GeospatialLayerStatus } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_VIGIA_API_URL ?? "http://localhost:8000";

export async function loadGeospatialLayers(signal?: AbortSignal): Promise<GeospatialLayerStatus[]> {
  const response = await fetch(`${API_BASE_URL}/api/geospatial/layers`, {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("GEOSPATIAL_LAYERS_UNAVAILABLE");
  return (await response.json()) as GeospatialLayerStatus[];
}

export function layerAvailability(
  layers: GeospatialLayerStatus[],
  acceptedLayers: string[],
): string {
  const matches = layers.filter((layer) => acceptedLayers.includes(layer.layer));
  if (!matches.length) return "NO DISPONIBLE";
  if (matches.some((layer) => layer.availability === "AVAILABLE")) return "DISPONIBLE";
  if (matches.some((layer) => layer.availability === "PARTIAL")) return "PARCIAL";
  return matches[0]?.availability ?? "NO DISPONIBLE";
}
