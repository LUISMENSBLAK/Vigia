"use client";

import { useEffect, useMemo, useState } from "react";

import {
  formatConfidenceInterval,
  formatMetric,
  loadValidationDatasets,
  loadValidationRun,
  loadValidationRuns,
  metricLabel,
} from "@/lib/validation";
import type {
  ValidationDatasetSummary,
  ValidationMetric,
  ValidationRunDetail,
  ValidationRunSummary,
} from "@/lib/validation";

function Hash({ value }: { value: string | null | undefined }) {
  return <code title={value ?? "NO DISPONIBLE"}>{value ? `${value.slice(0, 12)}…` : "NO DISPONIBLE"}</code>;
}

function MetricCard({ metric }: { metric: ValidationMetric }) {
  return (
    <article className={`validation-metric validation-metric--${metric.status.toLowerCase()}`}>
      <p>{metricLabel(metric.metric)}</p>
      <strong>{formatMetric(metric)}</strong>
      <dl>
        <div><dt>N</dt><dd>{metric.n}</dd></div>
        <div><dt>95 % CI</dt><dd>{formatConfidenceInterval(metric)}</dd></div>
      </dl>
      <small>{metric.reason ?? metric.population}</small>
    </article>
  );
}

export function ValidationWorkspace() {
  const [datasets, setDatasets] = useState<ValidationDatasetSummary[]>([]);
  const [runs, setRuns] = useState<ValidationRunSummary[]>([]);
  const [runId, setRunId] = useState("");
  const [detail, setDetail] = useState<ValidationRunDetail | null>(null);
  const [status, setStatus] = useState("CARGANDO VALIDACIÓN…");

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      loadValidationDatasets(controller.signal),
      loadValidationRuns(controller.signal),
    ]).then(([datasetRows, runRows]) => {
      setDatasets(datasetRows);
      setRuns(runRows);
      setRunId(runRows[0]?.id ?? "");
      setStatus(runRows.length ? "REPORTE VERIFICABLE DISPONIBLE" : "SIN VALIDATIONRUN PUBLICADO");
    }).catch(() => setStatus("NO DISPONIBLE: API DE VALIDACIÓN SIN RESPUESTA"));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    loadValidationRun(runId, controller.signal)
      .then(setDetail)
      .catch(() => setDetail(null));
    return () => controller.abort();
  }, [runId]);

  const dataset = datasets.find((item) => item.version === detail?.report.dataset_version)
    ?? datasets[0];
  const report = detail?.report;
  const headlineMetrics = useMemo(() => {
    const names = new Set([
      "event_recall",
      "alert_precision",
      "f1",
      "false_alerts_per_1000_km2_day",
      "median_sensor_observation_latency",
      "p90_localization_error",
    ]);
    return report?.metrics.filter((metric) => names.has(metric.metric)) ?? [];
  }, [report]);

  return (
    <main className="validation-page" id="main-content">
      <div className="validation-banner">VALIDACIÓN EXPERIMENTAL · NO ES UN CLAIM OPERACIONAL</div>
      <header className="validation-intro">
        <p className="eyebrow">VIGÍA SCIENTIFIC VALIDATION</p>
        <h1>Si no podemos defender la métrica, no la mostramos.</h1>
        <p>Dataset, split, engines y matching permanecen versionados. Cada resultado conserva N, incertidumbre, exclusiones y límites de cobertura.</p>
        <p className="validation-status" role="status" aria-live="polite">{status}</p>
      </header>

      <section className="validation-selector" aria-labelledby="validation-run-title">
        <div>
          <p className="eyebrow">REPORTE</p>
          <h2 id="validation-run-title">ValidationRun publicado</h2>
        </div>
        <label htmlFor="validation-run">Versión evaluada</label>
        <select id="validation-run" value={runId} onChange={(event) => setRunId(event.target.value)}>
          <option value="">SIN RUNS</option>
          {runs.map((run) => <option key={run.id} value={run.id}>{run.engine_version} · {run.split_role} · {run.commit_sha.slice(0, 8)}</option>)}
        </select>
      </section>

      <section className="validation-summary" aria-label="Resumen del dataset y split">
        <article>
          <p>Dataset</p>
          <strong>{dataset?.version ?? "NO DISPONIBLE"}</strong>
          <span>Hash <Hash value={dataset?.dataset_hash} /></span>
        </article>
        <article>
          <p>Alcance real</p>
          <strong>{dataset?.regions_covered.join(", ") || "NO DISPONIBLE"}</strong>
          <span>{dataset?.years_covered.join("–") || "AÑOS NO DISPONIBLES"}</span>
        </article>
        <article>
          <p>Referencias / controles</p>
          <strong>{dataset ? `${dataset.event_count.toLocaleString("es-ES")} / ${dataset.control_count}` : "SIN DATOS"}</strong>
          <span>Los controles no se inventan</span>
        </article>
        <article>
          <p>Split actual</p>
          <strong>{report?.split_role ?? "NO DISPONIBLE"}</strong>
          <span>TEST {dataset?.test_frozen ? "CONGELADO" : "NO VERIFICADO"}</span>
        </article>
      </section>

      <section className="validation-split" aria-labelledby="split-title">
        <div>
          <p className="eyebrow">INDEPENDENCIA</p>
          <h2 id="split-title">Split temporal por grupos de episodio</h2>
          <p>La asignación se congeló antes de consultar rendimiento. El periodo TEST no participa en esta ejecución.</p>
        </div>
        <dl>
          <div><dt>Development</dt><dd>{dataset?.development_count ?? "SIN DATOS"}</dd></div>
          <div><dt>Validation</dt><dd>{dataset?.validation_count ?? "SIN DATOS"}</dd></div>
          <div><dt>Independent test</dt><dd>{dataset?.test_count ?? "SIN DATOS"}</dd></div>
          <div><dt>Group leakage</dt><dd>{dataset?.leakage_checked ? "0 DETECTADO" : "NO VERIFICADO"}</dd></div>
        </dl>
      </section>

      <section className="validation-engine" aria-labelledby="engine-title">
        <div>
          <p className="eyebrow">BASELINE CONGELADO</p>
          <h2 id="engine-title">Lo que VIGÍA hacía antes de optimizar</h2>
        </div>
        <dl>
          <div><dt>Fusion</dt><dd>{report?.engine_versions.fusion ?? "NO DISPONIBLE"}</dd></div>
          <div><dt>Detection</dt><dd>{report?.engine_versions.detection ?? "NO DISPONIBLE"}</dd></div>
          <div><dt>Matcher</dt><dd>{report?.matcher_version ?? "NO DISPONIBLE"}</dd></div>
          <div><dt>Commit</dt><dd><Hash value={report?.code_commit} /></dd></div>
          <div><dt>Report hash</dt><dd><Hash value={report?.report_hash} /></dd></div>
          <div><dt>LIVE mutado</dt><dd>{report ? (report.live_state_mutated ? "ERROR" : "NO") : "NO VERIFICADO"}</dd></div>
        </dl>
      </section>

      <section className="validation-results" aria-labelledby="results-title">
        <header>
          <div><p className="eyebrow">RESULTADOS</p><h2 id="results-title">Métricas soportadas — y sus ausencias</h2></div>
          <p>No se dibujan gráficos: la muestra materializada todavía es insuficiente para una distribución defendible.</p>
        </header>
        <div className="validation-metric-grid">
          {headlineMetrics.length ? headlineMetrics.map((metric) => <MetricCard key={metric.metric} metric={metric} />) : <p>NO DISPONIBLE: no existe reporte cargado.</p>}
        </div>
        {report && <div className="validation-table-wrap"><table><caption>Tabla equivalente de todas las métricas</caption><thead><tr><th scope="col">Métrica</th><th scope="col">Estado</th><th scope="col">Resultado</th><th scope="col">N</th><th scope="col">95 % CI</th></tr></thead><tbody>{report.metrics.map((metric) => <tr key={metric.metric}><th scope="row">{metricLabel(metric.metric)}</th><td>{metric.status}</td><td>{formatMetric(metric)}</td><td>{metric.n}</td><td>{formatConfidenceInterval(metric)}</td></tr>)}</tbody></table></div>}
      </section>

      <section className="validation-availability" aria-labelledby="unavailable-title">
        <div><p className="eyebrow">NO DISPONIBLES</p><h2 id="unavailable-title">Un cero no sustituye una metodología ausente.</h2></div>
        <ul>{(report?.unavailable_metrics ?? ["PR_AUC", "BRIER_SCORE", "ECE", "CALIBRATION"]).map((metric) => <li key={metric}>{metricLabel(metric)} <span>NO DISPONIBLE</span></li>)}</ul>
      </section>

      <section className="validation-limitations" aria-labelledby="limitations-title">
        <div><p className="eyebrow">LIMITACIONES</p><h2 id="limitations-title">Hasta dónde llega esta evidencia</h2></div>
        <ul>{(report?.limitations ?? dataset?.coverage_limitations ?? ["NO DISPONIBLE"]).map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
        <nav aria-label="Documentación científica"><a href="/metodologia">Metodología</a><a href="/transparencia-ia">Transparencia IA</a><a href="/replay">Replay histórico</a></nav>
      </section>
    </main>
  );
}
