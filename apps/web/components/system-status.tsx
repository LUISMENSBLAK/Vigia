"use client";

import { useEffect, useState } from "react";

import { loadSystemStatus, overallState, unavailableStatus } from "@/lib/status";
import type { SystemStatus } from "@/lib/types";

import { StatusPill } from "./status-pill";

export function SystemStatusSummary() {
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadSystemStatus(controller.signal).then(setStatus).catch(() => setStatus(unavailableStatus));
    return () => controller.abort();
  }, []);

  if (!status) return <span className="status-loading">Verificando sistema…</span>;
  return (
    <span className="system-summary">
      <span>Estado del sistema</span>
      <StatusPill state={overallState(status)} />
    </span>
  );
}
