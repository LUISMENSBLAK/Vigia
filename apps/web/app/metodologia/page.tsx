import { SciencePage } from "@/components/science-page";

export default function MethodologyPage() { return <SciencePage eyebrow="METODOLOGÍA" title="Una cadena de evidencia antes que una cifra." introduction="VIGÍA se diseña como sistema multisensor trazable: conserva observaciones, transformaciones, modelos, parámetros y código." sections={[
  { title: "Observación", body: "Cada dato conserva fuente, sensing time, ingest time, calidad, versión y geometría." },
  { title: "Fusión y confianza", body: "EXPERIMENTAL: la evidencia considera familias, resolución, antigüedad, persistencia y contradicciones; todavía no produce una probabilidad calibrada." },
  { title: "Supervisión humana", body: "La evidencia automática no equivale a confirmación; las reglas y la revisión quedan explícitas." },
]} />; }
