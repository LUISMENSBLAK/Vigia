"use client";

import { useEffect, useState } from "react";

import { loadSystemStatus, unavailableStatus } from "@/lib/status";
import type { SourceHealth, SystemStatus } from "@/lib/types";

import { StatusPill } from "./status-pill";

function timestamp(value: string | null): string {
  return value ? new Date(value).toISOString() : "SIN DATOS";
}

function latency(value: number | null): string {
  if (value === null) return "SIN DATOS";
  if (value < 60) return `${value} s`;
  return `${Math.floor(value / 60)} min ${value % 60} s`;
}

function SourceRow({ source }: { source: SourceHealth }) {
  return (
    <article className="source-row">
      <header>
        <h2>{source.source}</h2>
        <StatusPill state={source.state} />
      </header>
      <dl>
        <div><dt>Última comprobación</dt><dd>{timestamp(source.checked_at)}</dd></div>
        <div><dt>Último dato observado</dt><dd>{timestamp(source.last_observed_at)}</dd></div>
        <div><dt>Último dato recibido</dt><dd>{timestamp(source.last_received_at)}</dd></div>
        <div><dt>Latencia observada</dt><dd>{latency(source.latency_seconds)}</dd></div>
      </dl>
      <p>{source.detail}</p>
      {source.error_code ? <code>{source.error_code}</code> : null}
    </article>
  );
}

export function StatusDashboard() {
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadSystemStatus(controller.signal).then(setStatus).catch(() => {
      if (!controller.signal.aborted) setStatus(unavailableStatus);
    });
    return () => controller.abort();
  }, []);

  return (
    <main className="status-page">
      <header>
        <p className="eyebrow">ESTADO DEL SISTEMA</p>
        <h1>Comprobaciones reales, sin optimismo implícito.</h1>
        <p>
          Una credencial configurada no convierte una fuente en operativa. Aquí se separan
          disponibilidad, observación, recepción y latencia.
        </p>
      </header>
      {!status ? (
        <div className="science-notice" role="status">
          <strong>VERIFICANDO</strong><span>Consultando la API VIGÍA…</span>
        </div>
      ) : (
        <section className="source-status-list" aria-label="Estado de fuentes y servicios">
          {status.sources.map((source) => <SourceRow key={source.source} source={source} />)}
        </section>
      )}
    </main>
  );
}
