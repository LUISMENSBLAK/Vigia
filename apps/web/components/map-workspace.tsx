"use client";

import dynamic from "next/dynamic";

import { SystemStatusSummary } from "./system-status";
import { VigiaLogo } from "./vigia-logo";

const MapCanvas = dynamic(() => import("./map-canvas").then((module) => module.MapCanvas), { ssr: false });

const layers = [
  "Riesgo VIGÍA", "Incendios activos", "Anomalías térmicas", "MTG", "VIIRS", "Sentinel",
  "Meteorología", "Viento", "Humedad", "Vegetación", "Combustible", "LiDAR", "Topografía", "Histórico",
];

export function MapWorkspace() {
  return (
    <main className="map-shell">
      <header className="map-header">
        <VigiaLogo />
        <SystemStatusSummary />
        <div className="map-header__controls">
          <span>UTC · Europe/Madrid</span>
          <button type="button" className="mode-switch" aria-label="Modo actual: Live">LIVE</button>
          <button type="button" className="map-language">ES / EN</button>
        </div>
      </header>
      <aside className="layers-panel" aria-label="Capas del mapa">
        <div className="panel-heading"><span>Capas de análisis</span><small>0 activas</small></div>
        <div className="layer-list">
          {layers.map((layer) => (
            <label key={layer}>
              <input type="checkbox" disabled />
              <span>{layer}</span>
              <small>Sin datos</small>
            </label>
          ))}
        </div>
        <p className="panel-note">Las capas se habilitan únicamente después de una ingestión verificada y trazable.</p>
      </aside>
      <section className="map-stage" aria-label="Área cartográfica">
        <MapCanvas />
        <div className="map-notice" role="status">
          <strong>Cartografía base</strong>
          <span>No se muestran detecciones, riesgo ni predicciones.</span>
        </div>
      </section>
      <aside className="incident-panel" aria-label="Detalle de incidente">
        <p className="eyebrow">ANÁLISIS DE INCIDENTE</p>
        <div className="empty-incident">
          <span className="empty-incident__mark">○</span>
          <h2>Sin incidentes verificados</h2>
          <p>Cuando exista una observación real, selecciona su geometría o consulta la lista accesible.</p>
          <a href="#incident-list">Ver lista textual</a>
        </div>
        <div id="incident-list" className="accessible-list">
          <strong>Lista accesible de incidentes</strong>
          <p>No hay incidentes que mostrar.</p>
        </div>
      </aside>
      <footer className="timeline" aria-label="Horizonte temporal">
        <div><strong>Ahora</strong><span>Sin predicción disponible</span></div>
        {["+15m", "+30m", "+1h", "+2h", "+4h", "+6h"].map((time) => <button key={time} disabled>{time}</button>)}
        <span className="timeline-warning">PREDICCIÓN EXPERIMENTAL · NO DISPONIBLE</span>
      </footer>
    </main>
  );
}
