import type { IncidentDetail, IncidentFeature } from "../lib/types";

export function IncidentDetailPanel({
  incident,
  detail,
}: {
  incident: IncidentFeature;
  detail: IncidentDetail | null;
}) {
  const [longitude, latitude] = incident.geometry.coordinates;
  const confirmed = incident.properties.state === "INCENDIO_CONFIRMADO";
  return (
    <div className="observation-detail incident-detail">
      <p className="eyebrow">
        {confirmed ? "INCIDENTE CONFIRMADO" : "INCIDENTE DERIVADO · NO CONFIRMADO"}
      </p>
      <h2>{incident.properties.code}</h2>
      <span className={`incident-state incident-state--${incident.properties.state.toLowerCase()}`}>
        {incident.properties.state.replaceAll("_", " ")}
      </span>
      <dl>
        <div><dt>Estado</dt><dd>{incident.properties.state.replaceAll("_", " ")}</dd></div>
        <div><dt>Ubicación</dt><dd>{latitude.toFixed(5)}, {longitude.toFixed(5)}</dd></div>
        <div><dt>Primera señal</dt><dd>{new Date(incident.properties.first_signal_at).toISOString()}</dd></div>
        <div><dt>Última observación</dt><dd>{new Date(incident.properties.last_observation_at).toISOString()}</dd></div>
        <div><dt>Observaciones</dt><dd>{incident.properties.observation_count}</dd></div>
        <div><dt>Familias</dt><dd>{incident.properties.source_families.join(", ")}</dd></div>
        <div><dt>Fuerza de evidencia</dt><dd>{incident.properties.evidence_strength ?? "SIN DATOS"}</dd></div>
        <div><dt>Calidad</dt><dd>{incident.properties.data_quality}</dd></div>
      </dl>
      <section className="incident-explanation" aria-labelledby="incident-why">
        <h3 id="incident-why">¿Por qué este estado?</h3>
        {detail ? (
          <ul>{detail.explanations.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        ) : <p>Información detallada no disponible.</p>}
      </section>
      <section className="incident-explanation" aria-labelledby="incident-missing">
        <h3 id="incident-missing">Información faltante</h3>
        {detail?.missing_information.length ? (
          <ul>{detail.missing_information.map((item) => <li key={item}>{item}</li>)}</ul>
        ) : <p>SIN DATOS</p>}
      </section>
      <details className="provenance-detail">
        <summary>Procedencia de la clasificación</summary>
        <dl>
          <div><dt>Reglas</dt><dd>{detail?.rule_version ?? "SIN DATOS"}</dd></div>
          <div><dt>Configuración</dt><dd><code>{detail?.configuration_hash ?? "SIN DATOS"}</code></dd></div>
        </dl>
      </details>
    </div>
  );
}
