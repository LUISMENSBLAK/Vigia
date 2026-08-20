import { IncidentDetailPanel } from "@/components/incident-detail";
import { SciencePage } from "@/components/science-page";
import { SiteHeader } from "@/components/site-header";
import type { IncidentDetail, IncidentFeature } from "@/lib/types";

export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  let detail: IncidentDetail | null = null;
  try {
    const response = await fetch(`${apiUrl}/api/incidents/${id}`, { cache: "no-store" });
    if (response.ok) detail = (await response.json()) as IncidentDetail;
  } catch {
    detail = null;
  }
  if (!detail) {
    return <SciencePage eyebrow="INCIDENTE" title={`Incidente ${id}`} introduction="No existe un incidente público verificable con este identificador en la base actual." notice="SIN DATOS. Esta ruta nunca completa una ficha con información simulada." sections={[
      { title: "Evidencias", body: "No disponibles." },
      { title: "Confianza", body: "No calculada." },
      { title: "Predicción", body: "No disponible." },
    ]} />;
  }
  const feature: IncidentFeature = {
    type: "Feature",
    geometry: detail.centroid,
    properties: {
      id: detail.id,
      code: detail.code,
      state: detail.state,
      first_signal_at: detail.first_signal_at,
      last_observation_at: detail.last_observation_at,
      observation_count: detail.observation_count,
      source_families: detail.source_families,
      evidence_strength: detail.evidence_strength as IncidentFeature["properties"]["evidence_strength"],
      data_quality: detail.data_quality as IncidentFeature["properties"]["data_quality"],
      data_age_seconds: Math.max(
        0,
        Math.floor((Date.now() - new Date(detail.last_observation_at).getTime()) / 1000),
      ),
      stale: detail.stale,
    },
  };
  return (
    <>
      <SiteHeader />
      <main className="incident-standalone">
        <IncidentDetailPanel incident={feature} detail={detail} />
      </main>
    </>
  );
}
