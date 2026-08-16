"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";

export function MapCanvas() {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: "https://demotiles.maplibre.org/style.json",
      center: [-3.7, 40.25],
      zoom: 5.15,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    return () => map.remove();
  }, []);

  return (
    <div
      ref={container}
      className="map-canvas"
      role="region"
      aria-label="Mapa base de España sin observaciones activas"
    />
  );
}
