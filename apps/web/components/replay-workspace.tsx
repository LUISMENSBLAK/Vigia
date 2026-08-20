"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";

import {
  createReplayRun,
  emptyReplayObservations,
  loadReplayCase,
  loadReplayCases,
  loadReplayObservations,
  loadReplayTimeline,
  replayStepLabel,
} from "@/lib/replay";
import type {
  ReplayCaseSummary,
  ReplayCaseDetail,
  ReplayIncident,
  ReplayObservationCollection,
  ReplayStep,
} from "@/lib/replay";

function incidentGeoJSON(incidents: ReplayIncident[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: incidents.map((incident) => ({
      type: "Feature",
      id: incident.replay_incident_id,
      geometry: { type: "Point", coordinates: incident.centroid },
      properties: {
        state: incident.state,
        observation_count: incident.observation_count,
      },
    })),
  };
}

function ReplayMap({
  incidents,
  observations,
  selectedCase,
  compare,
}: {
  incidents: ReplayIncident[];
  observations: ReplayObservationCollection;
  selectedCase?: ReplayCaseSummary;
  compare: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const instance = new maplibregl.Map({
      container: container.current,
      style: "https://demotiles.maplibre.org/style.json",
      center: [-3.7, 40.25],
      zoom: 5,
      attributionControl: false,
    });
    map.current = instance;
    instance.addControl(new maplibregl.NavigationControl(), "top-right");
    instance.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    instance.on("load", () => {
      instance.addSource("replay-incidents", { type: "geojson", data: incidentGeoJSON([]) });
      instance.addSource("replay-observations", {
        type: "geojson",
        data: emptyReplayObservations,
        cluster: true,
        clusterRadius: 36,
        clusterMaxZoom: 12,
      });
      instance.addLayer({
        id: "replay-observation-clusters",
        type: "circle",
        source: "replay-observations",
        filter: ["has", "point_count"],
        paint: {
          "circle-radius": ["step", ["get", "point_count"], 12, 20, 17, 100, 22],
          "circle-color": "#d9772e",
          "circle-stroke-color": "#fffef9",
          "circle-stroke-width": 1.5,
        },
      });
      instance.addLayer({
        id: "replay-observations",
        type: "circle",
        source: "replay-observations",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-radius": 5,
          "circle-color": "#ef9b57",
          "circle-stroke-color": "#fffef9",
          "circle-stroke-width": 1,
        },
      });
      instance.addLayer({
        id: "replay-incidents",
        type: "circle",
        source: "replay-incidents",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "observation_count"], 1, 7, 20, 16],
          "circle-color": [
            "match", ["get", "state"],
            "VIGILANCIA", "#aebbb6",
            "ANOMALIA", "#d9a441",
            "POSIBLE_IGNICION", "#d57a35",
            "PROBABLE_INCENDIO", "#ad5b38",
            "#839a91",
          ],
          "circle-stroke-color": "#fffef9",
          "circle-stroke-width": 2,
        },
      });
      instance.addSource("historical-reference", { type: "geojson", data: incidentGeoJSON([]) });
      instance.addLayer({
        id: "historical-reference",
        type: "circle",
        source: "historical-reference",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 11,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": "#7ad3ff",
          "circle-stroke-width": 3,
        },
      });
    });
    return () => {
      map.current = null;
      instance.remove();
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance?.isStyleLoaded()) return;
    (instance.getSource("replay-incidents") as maplibregl.GeoJSONSource | undefined)?.setData(
      incidentGeoJSON(incidents),
    );
    (instance.getSource("replay-observations") as maplibregl.GeoJSONSource | undefined)
      ?.setData(observations);
    const hasReference = selectedCase?.reference_longitude !== null
      && selectedCase?.reference_latitude !== null
      && selectedCase?.reference_longitude !== undefined
      && selectedCase?.reference_latitude !== undefined;
    const reference: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: hasReference ? [{
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [selectedCase.reference_longitude!, selectedCase.reference_latitude!],
        },
        properties: { plane: "GROUND_TRUTH" },
      }] : [],
    };
    (instance.getSource("historical-reference") as maplibregl.GeoJSONSource | undefined)
      ?.setData(reference);
    if (instance.getLayer("historical-reference")) {
      instance.setLayoutProperty(
        "historical-reference",
        "visibility",
        compare && hasReference ? "visible" : "none",
      );
    }
  }, [compare, incidents, observations, selectedCase]);

  return <div className="replay-map" ref={container} aria-label="Mapa del replay histórico" />;
}

function Availability({ values }: { values: Record<string, string | number> }) {
  const entries = Object.entries(values);
  if (!entries.length) return <p>NO DISPONIBLE</p>;
  return <dl>{entries.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>;
}

export function ReplayWorkspace() {
  const [cases, setCases] = useState<ReplayCaseSummary[]>([]);
  const [caseDetail, setCaseDetail] = useState<ReplayCaseDetail | null>(null);
  const [caseId, setCaseId] = useState("");
  const [timeline, setTimeline] = useState<ReplayStep[]>([]);
  const [runId, setRunId] = useState("");
  const [observations, setObservations] = useState(emptyReplayObservations);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [compare, setCompare] = useState(false);
  const [status, setStatus] = useState("CARGANDO CASOS…");
  const selectedCase = cases.find((item) => item.id === caseId);
  const step = timeline[index];

  useEffect(() => {
    const controller = new AbortController();
    loadReplayCases(controller.signal).then((items) => {
      setCases(items);
      setCaseId(items[0]?.id ?? "");
      setStatus(items.length ? "LISTO PARA EJECUTAR" : "SIN CASOS PUBLICADOS");
    }).catch(() => setStatus("NO DISPONIBLE: API REPLAY SIN RESPUESTA"));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!caseId) return;
    const controller = new AbortController();
    loadReplayCase(caseId, controller.signal)
      .then(setCaseDetail)
      .catch(() => setCaseDetail(null));
    return () => controller.abort();
  }, [caseId]);

  useEffect(() => {
    if (!playing || timeline.length < 2) return;
    const interval = window.setInterval(() => {
      setIndex((current) => {
        if (current >= timeline.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, Math.max(100, 1000 / speed));
    return () => window.clearInterval(interval);
  }, [playing, speed, timeline.length]);

  useEffect(() => {
    if (!runId || !step) return;
    const controller = new AbortController();
    loadReplayObservations(runId, step.as_of, controller.signal)
      .then(setObservations)
      .catch(() => setObservations(emptyReplayObservations));
    return () => controller.abort();
  }, [runId, step]);

  const incidentStates = useMemo(
    () => step?.incidents.map((incident) => `${incident.state} (${incident.observation_count})`) ?? [],
    [step],
  );

  async function runReplay() {
    if (!caseId) return;
    setPlaying(false);
    setObservations(emptyReplayObservations);
    setStatus("EJECUTANDO CON RELOJ HISTÓRICO…");
    try {
      const run = await createReplayRun(caseId);
      const steps = await loadReplayTimeline(run.id);
      setRunId(run.id);
      setTimeline(steps);
      setIndex(0);
      setStatus(run.deterministic && !run.live_state_mutated ? "REPLAY AISLADO COMPLETADO" : "ERROR DE AISLAMIENTO");
    } catch {
      setStatus("NO DISPONIBLE: NO SE PUDO EJECUTAR");
    }
  }

  return (
    <main className="replay-page">
      <div className="replay-banner">REPLAY HISTÓRICO · NO ES MONITORIZACIÓN LIVE</div>
      <header className="replay-intro">
        <p className="eyebrow">VIGÍA REPLAY</p>
        <h1>Lo que VIGÍA sabía, cuando podía saberlo.</h1>
        <p>La evidencia aparece únicamente al alcanzar su fecha de disponibilidad. La referencia oficial permanece separada y la comparación está desactivada por defecto.</p>
      </header>

      <section className="replay-toolbar" aria-label="Configuración del replay">
        <label>Caso histórico<select value={caseId} onChange={(event) => { setCaseId(event.target.value); setCaseDetail(null); setTimeline([]); setRunId(""); setObservations(emptyReplayObservations); setIndex(0); setCompare(false); }}><option value="">SIN CASOS</option>{cases.map((item) => <option key={item.id} value={item.id}>{item.official_start_time ? new Date(item.official_start_time).toLocaleDateString("es-ES") : "FECHA NO DISPONIBLE"} · {item.provinces.join(", ")} · {item.historical_event_code ?? item.case_key}</option>)}</select></label>
        <button type="button" onClick={runReplay} disabled={!caseId}>Ejecutar replay</button>
        <span role="status">{status}</span>
      </section>

      {selectedCase && <section className="replay-case-meta" aria-label="Ficha del caso seleccionado">
        <div><span>Región / provincia</span><strong>{[selectedCase.region, ...selectedCase.provinces].filter(Boolean).join(" · ") || "NO DISPONIBLE"}</strong></div>
        <div><span>Referencia</span><strong>{selectedCase.reference_sources.join(", ") || "NO DISPONIBLE"}</strong></div>
        <div><span>Calidad</span><strong>{selectedCase.reference_quality}</strong></div>
        <div><span>Ventana Replay</span><strong>{new Date(selectedCase.replay_start).toLocaleString("es-ES")} — {new Date(selectedCase.replay_end).toLocaleString("es-ES")}</strong></div>
      </section>}

      <section className="replay-stage">
        <div className="replay-knowledge">
          <h2>LO QUE VIGÍA SABÍA</h2>
          <strong>{replayStepLabel(step)}</strong>
          <p>{step ? `${step.visible_observation_count} observaciones visibles · ${step.candidate_count} candidatos` : "Ejecuta un caso para revelar la secuencia."}</p>
        </div>
        <ReplayMap incidents={step?.incidents ?? []} observations={observations} selectedCase={selectedCase} compare={compare} />
        <aside className="replay-panel">
          <h2>Estado en este instante</h2>
          <dl className="replay-metrics">
            <div><dt>Inputs visibles</dt><dd>{step?.visible_input_count ?? "SIN DATOS"}</dd></div>
            <div><dt>Observaciones</dt><dd>{step?.visible_observation_count ?? "SIN DATOS"}</dd></div>
            <div><dt>Incidentes</dt><dd>{step?.incidents.length ?? "SIN DATOS"}</dd></div>
            <div><dt>Riesgo</dt><dd>{step?.risk.availability ?? "NO DISPONIBLE"}</dd></div>
          </dl>
          <h3>Estados derivados</h3>
          <p>{incidentStates.length ? incidentStates.join(" · ") : "SIN INCIDENTES DERIVADOS"}</p>
          <h3>Disponibilidad</h3>
          <Availability values={step?.availability ?? {}} />
          <h3>Matriz del caso</h3>
          <Availability values={selectedCase?.sensor_availability ?? {}} />
          <h3>Fuentes VIGÍA</h3>
          <p>{selectedCase?.available_sources.join(", ") || "NO DISPONIBLE"}</p>
          <h3>Exclusiones temporales</h3>
          <Availability values={step?.exclusion_counts ?? {}} />
        </aside>
      </section>

      <section className="replay-controls" aria-label="Controles temporales">
        <button type="button" onClick={() => setIndex(0)} disabled={!timeline.length}>Inicio</button>
        <button type="button" onClick={() => setIndex((value) => Math.max(0, value - 1))} disabled={!timeline.length}>Paso anterior</button>
        <button type="button" onClick={() => setPlaying((value) => !value)} disabled={!timeline.length}>{playing ? "Pausar" : "Reproducir"}</button>
        <button type="button" onClick={() => setIndex((value) => Math.min(timeline.length - 1, value + 1))} disabled={!timeline.length}>Paso siguiente</button>
        <label>Velocidad<select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option><option value={8}>8×</option></select></label>
        <input aria-label="Instante del replay" type="range" min={0} max={Math.max(0, timeline.length - 1)} value={index} onChange={(event) => setIndex(Number(event.target.value))} disabled={!timeline.length} />
      </section>

      <section className="replay-truth">
        <label><input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} /> Activar comparación posterior con referencia oficial</label>
        <div aria-hidden={!compare} className={compare ? "" : "replay-truth--hidden"}>
          <h2>LO QUE SABEMOS AHORA</h2>
          {compare && selectedCase ? <dl><div><dt>Referencia</dt><dd>{selectedCase.historical_event_code ?? "NO DISPONIBLE"}</dd></div><div><dt>Inicio oficial</dt><dd>{selectedCase.official_start_time ? new Date(selectedCase.official_start_time).toLocaleString("es-ES") : "NO DISPONIBLE"}</dd></div><div><dt>Localización oficial</dt><dd>{selectedCase.reference_latitude !== null && selectedCase.reference_longitude !== null ? `${selectedCase.reference_latitude.toFixed(6)}, ${selectedCase.reference_longitude.toFixed(6)}` : "NO DISPONIBLE"}</dd></div><div><dt>Perímetros</dt><dd>{caseDetail?.reference_perimeters.length ? `${caseDetail.reference_perimeters.length} versiones` : "NO DISPONIBLE"}</dd></div><div><dt>Calidad</dt><dd>{selectedCase.reference_quality}</dd></div><div><dt>Fuente</dt><dd>{selectedCase.reference_sources.join(", ") || "NO DISPONIBLE"}</dd></div></dl> : <p>La verdad histórica está oculta durante la ejecución.</p>}
        </div>
      </section>
      <p className="replay-accessible">Alternativa textual: cada paso enumera hora, evidencia visible, incidentes derivados, disponibilidad, exclusiones y referencia oficial solo si la comparación se activa. Ningún color es el único indicador.</p>
    </main>
  );
}
