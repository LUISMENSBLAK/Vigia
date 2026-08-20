"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";

import { geospatialTileUrl } from "@/lib/geospatial";
import type {
  FireObservationCollection,
  FireObservationFeature,
  GeospatialCoverageCollection,
  GeospatialCoverageFeature,
  IncidentCollection,
  IncidentFeature,
} from "@/lib/types";

interface MapCanvasProps {
  observations: FireObservationCollection;
  incidents: IncidentCollection;
  showObservations: boolean;
  showIncidents: boolean;
  geospatialCoverage: GeospatialCoverageCollection;
  showTerrain: boolean;
  showVegetation: boolean;
  showLandCover: boolean;
  showDataCoverage: boolean;
  onSelectObservation: (observation: FireObservationFeature) => void;
  onSelectIncident: (incident: IncidentFeature) => void;
}

function preferredProduct(
  coverage: GeospatialCoverageCollection,
  layers: string[],
): GeospatialCoverageFeature | undefined {
  return coverage.features.find(
    (feature) =>
      layers.includes(feature.properties.layer)
      && feature.properties.raster_band !== null
      && ["AVAILABLE", "PARTIAL"].includes(feature.properties.availability),
  );
}

function syncRasterLayer(
  map: maplibregl.Map,
  id: string,
  product: GeospatialCoverageFeature | undefined,
  visible: boolean,
): void {
  const layerId = `${id}-raster`;
  const sourceId = `${id}-source`;
  if (map.getLayer(layerId)) map.removeLayer(layerId);
  if (map.getSource(sourceId)) map.removeSource(sourceId);
  if (!product) return;
  map.addSource(sourceId, {
    type: "raster",
    tiles: [geospatialTileUrl(product.properties.id)],
    tileSize: 256,
    minzoom: 0,
    maxzoom: 18,
  });
  map.addLayer({
    id: layerId,
    type: "raster",
    source: sourceId,
    layout: { visibility: visible ? "visible" : "none" },
    paint: { "raster-opacity": 0.72, "raster-fade-duration": 0 },
  });
}

function syncGeospatialLayers(
  map: maplibregl.Map,
  coverage: GeospatialCoverageCollection,
  visibility: { terrain: boolean; vegetation: boolean; landCover: boolean; coverage: boolean },
): void {
  const source = map.getSource("geospatial-coverage") as maplibregl.GeoJSONSource | undefined;
  source?.setData(coverage);
  syncRasterLayer(
    map,
    "geospatial-terrain",
    preferredProduct(coverage, ["ELEVATION", "SLOPE"]),
    visibility.terrain,
  );
  syncRasterLayer(
    map,
    "geospatial-vegetation",
    preferredProduct(coverage, ["NDVI", "NDMI", "NBR"]),
    visibility.vegetation,
  );
  if (map.getLayer("geospatial-land-cover")) {
    map.setLayoutProperty(
      "geospatial-land-cover",
      "visibility",
      visibility.landCover ? "visible" : "none",
    );
  }
  for (const layer of ["geospatial-coverage-fill", "geospatial-coverage-line"]) {
    if (map.getLayer(layer)) {
      map.setLayoutProperty(layer, "visibility", visibility.coverage ? "visible" : "none");
    }
  }
}

export function MapCanvas({
  observations,
  incidents,
  showObservations,
  showIncidents,
  geospatialCoverage,
  showTerrain,
  showVegetation,
  showLandCover,
  showDataCoverage,
  onSelectObservation,
  onSelectIncident,
}: MapCanvasProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const observationsRef = useRef(observations);
  const incidentsRef = useRef(incidents);
  const showObservationsRef = useRef(showObservations);
  const showIncidentsRef = useRef(showIncidents);
  const geospatialCoverageRef = useRef(geospatialCoverage);
  const geospatialVisibilityRef = useRef({
    terrain: showTerrain,
    vegetation: showVegetation,
    landCover: showLandCover,
    coverage: showDataCoverage,
  });

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: "https://demotiles.maplibre.org/style.json",
      center: [-3.7, 40.25],
      zoom: 5.15,
      attributionControl: false,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    map.on("load", () => {
      map.addSource("geospatial-coverage", {
        type: "geojson",
        data: geospatialCoverageRef.current,
      });
      map.addLayer({
        id: "geospatial-land-cover",
        type: "fill",
        source: "geospatial-coverage",
        filter: ["==", ["get", "layer"], "LAND_COVER"],
        layout: {
          visibility: geospatialVisibilityRef.current.landCover ? "visible" : "none",
        },
        paint: {
          "fill-color": "#7b8f56",
          "fill-opacity": 0.3,
          "fill-outline-color": "#53643b",
        },
      });
      map.addLayer({
        id: "geospatial-coverage-fill",
        type: "fill",
        source: "geospatial-coverage",
        layout: {
          visibility: geospatialVisibilityRef.current.coverage ? "visible" : "none",
        },
        paint: {
          "fill-color": [
            "match", ["get", "availability"],
            "AVAILABLE", "#4f8a75",
            "PARTIAL", "#c69a48",
            "#8b938e",
          ],
          "fill-opacity": 0.1,
        },
      });
      map.addLayer({
        id: "geospatial-coverage-line",
        type: "line",
        source: "geospatial-coverage",
        layout: {
          visibility: geospatialVisibilityRef.current.coverage ? "visible" : "none",
        },
        paint: { "line-color": "#315e51", "line-width": 1.4, "line-opacity": 0.8 },
      });
      syncGeospatialLayers(
        map,
        geospatialCoverageRef.current,
        geospatialVisibilityRef.current,
      );
      map.addSource("thermal-observations", {
        type: "geojson",
        data: observationsRef.current,
        cluster: true,
        clusterMaxZoom: 11,
        clusterRadius: 42,
      });
      map.addLayer({
        id: "thermal-clusters",
        type: "circle",
        source: "thermal-observations",
        filter: ["has", "point_count"],
        layout: { visibility: showObservationsRef.current ? "visible" : "none" },
        paint: {
          "circle-color": "#d9772e",
          "circle-radius": ["step", ["get", "point_count"], 15, 20, 19, 100, 24],
          "circle-stroke-color": "#fffef9",
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.88,
        },
      });
      map.addSource("derived-incidents", {
        type: "geojson",
        data: incidentsRef.current,
      });
      map.addLayer({
        id: "incident-points",
        type: "circle",
        source: "derived-incidents",
        layout: { visibility: showIncidentsRef.current ? "visible" : "none" },
        paint: {
          "circle-color": [
            "match",
            ["get", "state"],
            "VIGILANCIA", "#839a91",
            "ANOMALIA", "#c69a48",
            "POSIBLE_IGNICION", "#d57a35",
            "PROBABLE_INCENDIO", "#ad5b38",
            "INCENDIO_CONFIRMADO", "#b8352e",
            "DESCARTADO", "#66736e",
            "#839a91",
          ],
          "circle-radius": [
            "interpolate", ["linear"], ["get", "observation_count"], 2, 8, 20, 15,
          ],
          "circle-stroke-color": "#fffef9",
          "circle-stroke-width": 2,
          "circle-opacity": 0.9,
        },
      });
      map.addLayer({
        id: "thermal-cluster-count",
        type: "symbol",
        source: "thermal-observations",
        filter: ["has", "point_count"],
        layout: {
          "visibility": showObservationsRef.current ? "visible" : "none",
          "text-field": ["get", "point_count_abbreviated"],
          "text-size": 11,
        },
        paint: { "text-color": "#fffef9" },
      });
      map.addLayer({
        id: "thermal-points",
        type: "circle",
        source: "thermal-observations",
        filter: ["!", ["has", "point_count"]],
        layout: { visibility: showObservationsRef.current ? "visible" : "none" },
        paint: {
          "circle-color": "#e17a2d",
          "circle-radius": 5,
          "circle-stroke-color": "#fffef9",
          "circle-stroke-width": 1.5,
        },
      });
      map.on("click", "thermal-clusters", async (event) => {
        const feature = map.queryRenderedFeatures(event.point, { layers: ["thermal-clusters"] })[0];
        const clusterId = feature?.properties?.cluster_id;
        const source = map.getSource("thermal-observations") as maplibregl.GeoJSONSource;
        if (!feature || typeof clusterId !== "number") return;
        const zoom = await source.getClusterExpansionZoom(clusterId);
        const coordinates = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
        map.easeTo({ center: coordinates, zoom });
      });
      map.on("click", "thermal-points", (event) => {
        const id = event.features?.[0]?.properties?.id;
        const selected = observationsRef.current.features.find(
          (observation) => observation.properties.id === id,
        );
        if (selected) onSelectObservation(selected);
      });
      map.on("click", "incident-points", (event) => {
        const id = event.features?.[0]?.properties?.id;
        const selected = incidentsRef.current.features.find(
          (incident) => incident.properties.id === id,
        );
        if (selected) onSelectIncident(selected);
      });
      map.on("click", "geospatial-coverage-fill", (event) => {
        const properties = event.features?.[0]?.properties;
        if (!properties || !event.lngLat) return;
        const observedAt = properties.observed_at || "NO DISPONIBLE";
        const resolution = properties.output_resolution_m
          ? `${properties.output_resolution_m} m`
          : "NO DISPONIBLE";
        new maplibregl.Popup({ closeButton: true, maxWidth: "320px" })
          .setLngLat(event.lngLat)
          .setHTML(
            `<strong>${String(properties.layer)}</strong><br>`
              + `Estado: ${String(properties.availability)}<br>`
              + `Fuente: ${String(properties.source)}<br>`
              + `Fecha: ${String(observedAt)}<br>`
              + `Resolución: ${String(resolution)}`,
          )
          .addTo(map);
      });
      for (const layer of ["thermal-clusters", "thermal-points", "incident-points"]) {
        map.on("mouseenter", layer, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layer, () => {
          map.getCanvas().style.cursor = "";
        });
      }
    });
    return () => {
      mapRef.current = null;
      map.remove();
    };
  }, [onSelectIncident, onSelectObservation]);

  useEffect(() => {
    observationsRef.current = observations;
    const source = mapRef.current?.getSource("thermal-observations") as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(observations);
  }, [observations]);

  useEffect(() => {
    incidentsRef.current = incidents;
    const source = mapRef.current?.getSource("derived-incidents") as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(incidents);
  }, [incidents]);

  useEffect(() => {
    geospatialCoverageRef.current = geospatialCoverage;
    geospatialVisibilityRef.current = {
      terrain: showTerrain,
      vegetation: showVegetation,
      landCover: showLandCover,
      coverage: showDataCoverage,
    };
    const map = mapRef.current;
    if (map?.isStyleLoaded()) {
      syncGeospatialLayers(map, geospatialCoverage, geospatialVisibilityRef.current);
    }
  }, [geospatialCoverage, showTerrain, showVegetation, showLandCover, showDataCoverage]);

  useEffect(() => {
    showObservationsRef.current = showObservations;
    for (const layer of ["thermal-clusters", "thermal-cluster-count", "thermal-points"]) {
      if (mapRef.current?.getLayer(layer)) {
        mapRef.current.setLayoutProperty(
          layer,
          "visibility",
          showObservations ? "visible" : "none",
        );
      }
    }
  }, [showObservations]);

  useEffect(() => {
    showIncidentsRef.current = showIncidents;
    if (mapRef.current?.getLayer("incident-points")) {
      mapRef.current.setLayoutProperty(
        "incident-points",
        "visibility",
        showIncidents ? "visible" : "none",
      );
    }
  }, [showIncidents]);

  return (
    <div
      ref={container}
      className="map-canvas"
      role="region"
      aria-label={
        observations.features.length
          ? `Mapa de España con ${observations.features.length} observaciones térmicas y ${incidents.features.length} incidentes derivados`
          : `Mapa base de España con ${incidents.features.length} incidentes derivados`
      }
    />
  );
}
