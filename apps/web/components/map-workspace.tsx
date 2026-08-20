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
import {
  emptyIncidents,
  incidentLabel,
  loadIncidentDetail,
  loadIncidents,
  unavailableIncidents,
} from "@/lib/incidents";
import { layerAvailability, loadGeospatialLayers } from "@/lib/geospatial";
import type {
  FireObservationCollection,
  FireObservationFeature,
  IncidentCollection,
  IncidentDetail,
  IncidentFeature,
  GeospatialLayerStatus,
} from "@/lib/types";

import { IncidentDetailPanel } from "./incident-detail";
import { StatusPill } from "./status-pill";
import { SystemStatusSummary } from "./system-status";
import { VigiaLogo } from "./vigia-logo";

const MapCanvas = dynamic(() => import("./map-canvas").then((module) => module.MapCanvas), {
  ssr: false,
});

const inactiveLayers = [
  "MTG-FCI",
  "Sentinel",
  "Meteorología",
  "Viento",
  "Humedad",
  "Combustible",
  "LiDAR",
  "Histórico",
];

const geospatialLayers = [
  { label: "Terrain", codes: ["ELEVATION", "SLOPE", "ASPECT", "TERRAIN_RUGGEDNESS"] },
  { label: "Vegetation", codes: ["NDVI", "NDMI", "NBR"] },
  { label: "Land Cover", codes: ["LAND_COVER"] },
  {
    label: "Cobertura de datos",
    codes: [
      "ELEVATION",
      "SLOPE",
      "ASPECT",
      "TERRAIN_RUGGEDNESS",
      "NDVI",
      "NDMI",
      "NBR",
      "LAND_COVER",
      "LIDAR_DTM",
      "LIDAR_DSM",
      "CANOPY_HEIGHT",
    ],
  },
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
  const [incidents, setIncidents] = useState<IncidentCollection>(emptyIncidents);
  const [selectedObservation, setSelectedObservation] = useState<FireObservationFeature | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<IncidentFeature | null>(null);
  const [incidentDetail, setIncidentDetail] = useState<IncidentDetail | null>(null);
  const [observationsLoading, setObservationsLoading] = useState(true);
  const [incidentsLoading, setIncidentsLoading] = useState(true);
  const [showObservations, setShowObservations] = useState(true);
  const [showIncidents, setShowIncidents] = useState(true);
  const [geospatialStatus, setGeospatialStatus] = useState<GeospatialLayerStatus[]>([]);
  const [geospatialLoading, setGeospatialLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    loadFireObservations(controller.signal)
      .then((collection) => {
        setObservations(collection);
      })
      .catch(() => {
        if (!controller.signal.aborted) setObservations(unavailableObservations);
      })
      .finally(() => {
        if (!controller.signal.aborted) setObservationsLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadGeospatialLayers(controller.signal)
      .then(setGeospatialStatus)
      .catch(() => {
        if (!controller.signal.aborted) setGeospatialStatus([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setGeospatialLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadIncidents(controller.signal)
      .then(setIncidents)
      .catch(() => {
        if (!controller.signal.aborted) setIncidents(unavailableIncidents);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIncidentsLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedIncident) return;
    const controller = new AbortController();
    loadIncidentDetail(selectedIncident.properties.id, controller.signal)
      .then(setIncidentDetail)
      .catch(() => {
        if (!controller.signal.aborted) setIncidentDetail(null);
      });
    return () => controller.abort();
  }, [selectedIncident]);

  const selectObservation = useCallback((observation: FireObservationFeature) => {
    setSelectedObservation(observation);
    setSelectedIncident(null);
    setIncidentDetail(null);
  }, []);
  const selectIncident = useCallback((incident: IncidentFeature) => {
    setSelectedIncident(incident);
    setSelectedObservation(null);
  }, []);
  const hasObservations = observations.features.length > 0;
  const hasIncidents = incidents.features.length > 0;
  const loading = observationsLoading || incidentsLoading;

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
          <span>Capas de análisis</span>
          <small>{Number(showObservations) + Number(showIncidents)} activas</small>
        </div>
        <div className="layer-list">
          <label>
            <input
              type="checkbox"
              checked={showObservations}
              onChange={(event) => setShowObservations(event.target.checked)}
            />
            <span>Observaciones térmicas</span>
            <small>{observationsLoading ? "Verificando" : observations.metadata.count}</small>
          </label>
          <label>
            <input
              type="checkbox"
              checked={showIncidents}
              onChange={(event) => setShowIncidents(event.target.checked)}
            />
            <span>Incidentes derivados</span>
            <small>{incidentsLoading ? "Verificando" : incidents.metadata.count}</small>
          </label>
          {geospatialLayers.map((layer) => {
            const availability = geospatialLoading
              ? "VERIFICANDO"
              : layerAvailability(geospatialStatus, layer.codes);
            return (
              <label key={layer.label}>
                <input type="checkbox" disabled />
                <span>{layer.label}</span>
                <small>{availability}</small>
              </label>
            );
          })}
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
        <MapCanvas
          observations={observations}
          incidents={incidents}
          showObservations={showObservations}
          showIncidents={showIncidents}
          onSelectObservation={selectObservation}
          onSelectIncident={selectIncident}
        />
        <div className={`map-notice map-notice--${observations.metadata.data_state.toLowerCase()}`} role="status">
          <strong>{loading ? "VERIFICANDO" : observations.metadata.data_state}</strong>
          <span>
            {loading
              ? "Consultando observaciones e incidentes persistidos…"
              : `${observations.metadata.message} · ${incidents.metadata.message}`}
          </span>
        </div>
        <div className="map-legend" aria-label="Simbología de incidentes">
          <strong>Incidentes</strong>
          <span><i className="legend-watch" />Vigilancia</span>
          <span><i className="legend-anomaly" />Anomalía</span>
          <span><i className="legend-possible" />Posible ignición</span>
          <span><i className="legend-probable" />Probable incendio</span>
        </div>
      </section>
      <aside className="incident-panel" aria-label="Detalle y alternativa textual de observaciones">
        {selectedIncident ? (
          <IncidentDetailPanel
            incident={selectedIncident}
            detail={incidentDetail?.id === selectedIncident.properties.id ? incidentDetail : null}
          />
        ) : selectedObservation ? (
          <ObservationDetail observation={selectedObservation} />
        ) : (
          <div className="empty-incident">
            <StatusPill state={incidents.metadata.data_state} />
            <h2>{loading ? "Verificando evidencia" : "Sin incidentes verificados"}</h2>
            <p>
              {loading
                ? "Consultando la API VIGÍA."
                : "Selecciona una observación o un incidente derivado. Ningún hotspot aislado equivale a un incendio."}
            </p>
          </div>
        )}
        <div id="observation-list" className="accessible-list">
          <label htmlFor="observation-selector">Lista textual de observaciones</label>
          {hasObservations ? (
            <select
              id="observation-selector"
              value={selectedObservation?.properties.id ?? ""}
              onChange={(event) => {
                const observation = observations.features.find(
                  (item) => item.properties.id === event.target.value,
                );
                if (observation) selectObservation(observation);
              }}
            >
              <option value="">Seleccionar observación</option>
              {observations.features.map((observation) => (
                <option key={observation.properties.id} value={observation.properties.id}>
                  {observationLabel(observation)}
                </option>
              ))}
            </select>
          ) : <p>{loading ? "Verificando…" : observations.metadata.message}</p>}
          <label htmlFor="incident-selector">Lista textual de incidentes derivados</label>
          {hasIncidents ? (
            <select
              id="incident-selector"
              value={selectedIncident?.properties.id ?? ""}
              onChange={(event) => {
                const incident = incidents.features.find(
                  (item) => item.properties.id === event.target.value,
                );
                if (incident) selectIncident(incident);
              }}
            >
              <option value="">Seleccionar incidente</option>
              {incidents.features.map((incident) => (
                <option key={incident.properties.id} value={incident.properties.id}>
                  {incidentLabel(incident)}
                </option>
              ))}
            </select>
          ) : <p>{incidentsLoading ? "Verificando…" : incidents.metadata.message}</p>}
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
