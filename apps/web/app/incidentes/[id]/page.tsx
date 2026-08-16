import { SciencePage } from "@/components/science-page";

export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SciencePage eyebrow="INCIDENTE" title={`Incidente ${id}`} introduction="No existe un incidente verificado con este identificador en la base actual." notice="Sin datos. Esta ruta nunca completa una ficha con información simulada." sections={[
    { title: "Evidencias", body: "No disponibles." },
    { title: "Confianza", body: "No calculada." },
    { title: "Predicción", body: "No disponible." },
  ]} />;
}
