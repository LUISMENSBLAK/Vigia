import { SciencePage } from "@/components/science-page";

export default function StatusPage() { return <SciencePage eyebrow="ESTADO DEL SISTEMA" title="Fuentes externas y workers, sin optimismo implícito." introduction="La disponibilidad solo será OPERATIVA después de una comprobación real. La ausencia de datos, los errores y la edad se muestran por separado." notice="La API local expone el estado inicial; todas las fuentes externas permanecen SIN DATOS hasta su primera ingestión verificada." sections={[
  { title: "NASA FIRMS", body: "Worker inicial implementado; exige NASA_FIRMS_MAP_KEY y falla de forma explícita si falta." },
  { title: "AEMET, EUMETSAT y Copernicus", body: "Workers planificados para fases posteriores; no se emite estado operativo." },
  { title: "Base de datos", body: "La migración PostGIS y RLS está preparada, pendiente de aplicar y verificar en un proyecto Supabase." },
]} />; }
