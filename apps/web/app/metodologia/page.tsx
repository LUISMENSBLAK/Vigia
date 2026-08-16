import { SciencePage } from "@/components/science-page";

export default function MethodologyPage() { return <SciencePage eyebrow="METODOLOGÍA" title="Una cadena de evidencia antes que una cifra." introduction="VIGÍA se diseña como sistema multisensor trazable: conserva observaciones, transformaciones, modelos, parámetros y código." sections={[
  { title: "Observación", body: "Cada dato conserva fuente, sensing time, ingest time, calidad, versión y geometría." },
  { title: "Fusión y confianza", body: "La probabilidad calibrada considera correlación, resolución, antigüedad, persistencia y contradicciones." },
  { title: "Supervisión humana", body: "Una probabilidad alta no equivale a confirmación; las reglas de evidencia y revisión quedan explícitas." },
]} />; }
