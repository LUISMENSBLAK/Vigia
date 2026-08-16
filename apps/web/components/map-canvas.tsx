"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";

import type { FireObservationCollection, FireObservationFeature } from "@/lib/types";

interface MapCanvasProps {
  observations: FireObservationCollection;
  onSelect: (observation: FireObservationFeature) => void;
}

export function MapCanvas({ observations, onSelect }: MapCanvasProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const observationsRef = useRef(observations);

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
        paint: {
          "circle-color": "#d9772e",
          "circle-radius": ["step", ["get", "point_count"], 15, 20, 19, 100, 24],
          "circle-stroke-color": "#fffef9",
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.88,
        },
      });
      map.addLayer({
        id: "thermal-cluster-count",
        type: "symbol",
        source: "thermal-observations",
        filter: ["has", "point_count"],
        layout: {
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
        if (selected) onSelect(selected);
      });
      for (const layer of ["thermal-clusters", "thermal-points"]) {
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
  }, [onSelect]);

  useEffect(() => {
    observationsRef.current = observations;
    const source = mapRef.current?.getSource("thermal-observations") as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(observations);
  }, [observations]);

  return (
    <div
      ref={container}
      className="map-canvas"
      role="region"
      aria-label={
        observations.features.length
          ? `Mapa de España con ${observations.features.length} observaciones térmicas reales`
          : "Mapa base de España sin observaciones térmicas disponibles"
      }
    />
  );
}
