import type { GeospatialCoverageCollection, GeospatialLayerStatus } from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_VIGIA_API_URL ?? "http://localhost:8000";

export const emptyGeospatialCoverage: GeospatialCoverageCollection = {
  type: "FeatureCollection",
  features: [],
  as_of: new Date(0).toISOString(),
};

export async function loadGeospatialLayers(signal?: AbortSignal): Promise<GeospatialLayerStatus[]> {
  const response = await fetch(`${API_BASE_URL}/api/geospatial/layers`, {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("GEOSPATIAL_LAYERS_UNAVAILABLE");
  return (await response.json()) as GeospatialLayerStatus[];
}

export async function loadGeospatialCoverage(
  signal?: AbortSignal,
): Promise<GeospatialCoverageCollection> {
  const parameters = new URLSearchParams({
    west: "-18.5",
    south: "27.5",
    east: "4.5",
    north: "44.5",
    limit: "1000",
  });
  const response = await fetch(`${API_BASE_URL}/api/geospatial/coverage?${parameters}`, {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("GEOSPATIAL_COVERAGE_UNAVAILABLE");
  return (await response.json()) as GeospatialCoverageCollection;
}

export function geospatialTileUrl(productId: string): string {
  return `${API_BASE_URL}/api/geospatial/tiles/${encodeURIComponent(productId)}/{z}/{x}/{y}.png`;
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
