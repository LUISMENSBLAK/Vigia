"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import {
  emptyObservations,
  formatAge,
  loadFireObservations,
  observationLabel,
  unavailableObservations,
} from "@/lib/observations";
import type { FireObservationCollection, FireObservationFeature } from "@/lib/types";

import { StatusPill } from "./status-pill";
import { SystemStatusSummary } from "./system-status";
import { VigiaLogo } from "./vigia-logo";

const MapCanvas = dynamic(() => import("./map-canvas").then((module) => module.MapCanvas), {
  ssr: false,
});

const inactiveLayers = [
  "Incidentes",
  "MTG-FCI",
  "Sentinel",
  "Meteorología",
  "Viento",
  "Humedad",
  "Vegetación",
  "Combustible",
  "LiDAR",
  "Topografía",
  "Histórico",
];

function valueOrNoData(value: string | number | null, suffix = ""): string {
  return value === null || value === "" ? "SIN DATOS" : `${value}${suffix}`;
}

function ObservationDetail({ observation }: { observation: FireObservationFeature }) {
  const [longitude, latitude] = observation.geometry.coordinates;
  const provenance = observation.properties.provenance;
  return (
    <div className="observation-detail">
      <p className="eyebrow">OBSERVACIÓN TÉRMICA · NO EQUIVALE A INCENDIO</p>
      <h2>{observation.properties.sensor}</h2>
      <dl>
        <div><dt>Fuente</dt><dd>{observation.properties.source}</dd></div>
        <div><dt>Satélite</dt><dd>{observation.properties.platform}</dd></div>
        <div><dt>Sensor</dt><dd>{observation.properties.sensor}</dd></div>
        <div><dt>Ubicación</dt><dd>{latitude.toFixed(5)}, {longitude.toFixed(5)}</dd></div>
        <div><dt>Observado</dt><dd>{new Date(observation.properties.observed_at).toISOString()}</dd></div>
        <div><dt>Recibido</dt><dd>{new Date(observation.properties.received_at).toISOString()}</dd></div>
        <div><dt>Edad al consultar</dt><dd>{formatAge(observation.properties.age_seconds)}</dd></div>
        <div><dt>Confidence original</dt><dd>{valueOrNoData(observation.properties.confidence_raw)}</dd></div>
        <div><dt>FRP</dt><dd>{valueOrNoData(observation.properties.frp_mw, " MW")}</dd></div>
        <div><dt>Día / noche</dt><dd>{valueOrNoData(observation.properties.daynight)}</dd></div>
      </dl>
      <details className="provenance-detail">
        <summary>Procedencia técnica</summary>
        {provenance ? (
          <dl>
            <div><dt>Transformación</dt><dd>{String(provenance.transformation ?? "SIN DATOS")}</dd></div>
            <div><dt>Versión de código</dt><dd>{String(provenance.code_commit ?? "SIN DATOS")}</dd></div>
            <div><dt>Hash de salida</dt><dd><code>{String(provenance.output_hash ?? "SIN DATOS")}</code></dd></div>
          </dl>
        ) : <p>SIN DATOS</p>}
      </details>
    </div>
  );
}

export function MapWorkspace() {
  const [observations, setObservations] = useState<FireObservationCollection>(emptyObservations);
  const [selected, setSelected] = useState<FireObservationFeature | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    loadFireObservations(controller.signal)
      .then((collection) => {
        setObservations(collection);
        setSelected(collection.features[0] ?? null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setObservations(unavailableObservations);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const selectObservation = useCallback((observation: FireObservationFeature) => {
    setSelected(observation);
  }, []);
  const hasData = observations.features.length > 0;

  return (
    <main className="map-shell">
      <header className="map-header">
        <VigiaLogo />
        <SystemStatusSummary />
        <div className="map-header__controls">
          <span>Datos UTC · interfaz Europe/Madrid</span>
          <span className="mode-switch">LIVE</span>
        </div>
      </header>
      <aside className="layers-panel" aria-label="Capas del mapa">
        <div className="panel-heading">
          <span>Capas de análisis</span><small>{hasData ? "1 activa" : "0 activas"}</small>
        </div>
        <div className="layer-list">
          <label>
            <input type="checkbox" checked={hasData} disabled={!hasData} readOnly />
            <span>Anomalías térmicas</span>
            <small>{loading ? "Verificando" : hasData ? observations.metadata.count : "Sin datos"}</small>
          </label>
          {inactiveLayers.map((layer) => (
            <label key={layer}>
              <input type="checkbox" disabled />
              <span>{layer}</span>
              <small>En preparación</small>
            </label>
          ))}
        </div>
        <p className="panel-note">
          Los puntos son observaciones satelitales. No representan incendios confirmados.
        </p>
      </aside>
      <section className="map-stage" aria-label="Área cartográfica">
        <MapCanvas observations={observations} onSelect={selectObservation} />
        <div className={`map-notice map-notice--${observations.metadata.data_state.toLowerCase()}`} role="status">
          <strong>{loading ? "VERIFICANDO" : observations.metadata.data_state}</strong>
          <span>{loading ? "Consultando observaciones persistidas…" : observations.metadata.message}</span>
        </div>
      </section>
      <aside className="incident-panel" aria-label="Detalle y alternativa textual de observaciones">
        {selected ? <ObservationDetail observation={selected} /> : (
          <div className="empty-incident">
            <StatusPill state={observations.metadata.data_state} />
            <h2>{loading ? "Verificando observaciones" : observations.metadata.data_state === "ERROR" ? "NO DISPONIBLE" : "SIN OBSERVACIONES ACTIVAS"}</h2>
            <p>{loading ? "Consultando la API VIGÍA." : observations.metadata.message}</p>
          </div>
        )}
        <div id="observation-list" className="accessible-list">
          <label htmlFor="observation-selector">Lista textual de observaciones</label>
          {hasData ? (
            <select
              id="observation-selector"
              value={selected?.properties.id ?? ""}
              onChange={(event) => {
                const observation = observations.features.find(
                  (item) => item.properties.id === event.target.value,
                );
                if (observation) setSelected(observation);
              }}
            >
              {observations.features.map((observation) => (
                <option key={observation.properties.id} value={observation.properties.id}>
                  {observationLabel(observation)}
                </option>
              ))}
            </select>
          ) : <p>{loading ? "Verificando…" : observations.metadata.message}</p>}
        </div>
      </aside>
      <footer className="timeline" aria-label="Horizonte temporal">
        <div><strong>Observado</strong><span>Sin predicción disponible</span></div>
        {["+15m", "+30m", "+1h", "+2h", "+4h", "+6h"].map((time) => <button key={time} disabled>{time}</button>)}
        <span className="timeline-warning">PREDICCIÓN EXPERIMENTAL · NO DISPONIBLE</span>
      </footer>
    </main>
  );
}
