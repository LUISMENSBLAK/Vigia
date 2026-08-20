"use client";

import { FormEvent, useState } from "react";

import {
  loadRiskContext,
  loadRiskForecast,
  type RiskAssessment,
  type RiskContext,
  type RiskForecast,
} from "@/lib/risk";

function Assessment({ assessment }: { assessment: RiskAssessment }) {
  return (
    <article className="risk-result">
      <header>
        <div>
          <span>Índice ambiental experimental</span>
          <strong>{assessment.experimental_index?.toFixed(1) ?? "NO DISPONIBLE"}</strong>
        </div>
        <div>
          <span>Clase descriptiva</span>
          <strong>{assessment.risk_class}</strong>
        </div>
        <div>
          <span>Calidad</span>
          <strong>{assessment.data_quality}</strong>
        </div>
      </header>
      <p className="science-warning">{assessment.disclaimer}</p>
      <dl>
        {Object.entries(assessment.component_scores).map(([name, score]) => (
          <div key={name}>
            <dt>{name}</dt>
            <dd>{score === null ? "NO DISPONIBLE" : `${score.toFixed(1)} / 100`}</dd>
          </div>
        ))}
        <div><dt>Válido</dt><dd>{new Date(assessment.valid_at).toISOString()}</dd></div>
        <div><dt>Versión</dt><dd>{assessment.engine_version}</dd></div>
      </dl>
      {assessment.missing_components.length > 0 && (
        <p>Faltantes: {assessment.missing_components.join(", ")}</p>
      )}
      <details>
        <summary>Explicaciones y razones</summary>
        <ul>
          {[...assessment.explanations, ...assessment.reason_codes].map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </details>
    </article>
  );
}

export function RiskDashboard() {
  const [latitude, setLatitude] = useState("40.65");
  const [longitude, setLongitude] = useState("-4.68");
  const [context, setContext] = useState<RiskContext | null>(null);
  const [forecast, setForecast] = useState<RiskForecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = async (signal?: AbortSignal) => {
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setError("Coordenadas no válidas.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [current, horizons] = await Promise.all([
        loadRiskContext(lat, lon, signal),
        loadRiskForecast(lat, lon, signal),
      ]);
      setContext(current);
      setForecast(horizons);
    } catch {
      if (!signal?.aborted) setError("NO DISPONIBLE: la API de riesgo no respondió.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void query();
  };

  return (
    <main className="risk-page">
      <header>
        <p className="eyebrow">VIGÍA RISK ENGINE · BASELINE V1</p>
        <h1>Condiciones ambientales, no presencia de fuego.</h1>
        <p>
          Consulta nacional por coordenada. Ávila es solo el punto inicial de validación;
          cualquier coordenada española usa el mismo contrato.
        </p>
      </header>
      <form onSubmit={submit} className="risk-query">
        <label>Latitud<input value={latitude} onChange={(e) => setLatitude(e.target.value)} /></label>
        <label>Longitud<input value={longitude} onChange={(e) => setLongitude(e.target.value)} /></label>
        <button type="submit" disabled={loading}>{loading ? "Verificando…" : "Consultar"}</button>
      </form>
      {error && <p role="alert" className="science-warning">{error}</p>}
      {context && (
        <section aria-live="polite">
          <h2>Actual / análisis</h2>
          <p>{context.message}</p>
          {context.assessment ? <Assessment assessment={context.assessment} /> : <strong>NO DISPONIBLE</strong>}
        </section>
      )}
      {forecast && (
        <section>
          <h2>Horizontes reales persistidos</h2>
          <p>{forecast.message}</p>
          <div className="risk-horizons">
            {forecast.forecasts.length > 0
              ? forecast.forecasts.map((item) => <Assessment key={item.id} assessment={item} />)
              : <strong>NO DISPONIBLE</strong>}
          </div>
        </section>
      )}
    </main>
  );
}
