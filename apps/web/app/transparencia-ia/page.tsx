import { SciencePage } from "@/components/science-page";

export default function TransparencyPage() { return <SciencePage eyebrow="TRANSPARENCIA DE IA" title="Cómo obtuvo VIGÍA este resultado." introduction="Cada predicción futura podrá abrir su ficha de procedencia, modelo, variables, calidad, incertidumbre y actualización." sections={[
  { title: "Dataset y protocolo", body: "El dataset, split, protocolo, matcher, configuración y commit de cada ValidationRun quedan congelados y enlazados por hashes auditables." },
  { title: "Métricas y limitaciones", body: "Cada métrica conserva población, elegibilidad, N e incertidumbre. Lo que no puede calcularse aparece como NO DISPONIBLE." },
  { title: "Versiones y acceso TEST", body: "Los modelos y baselines se identifican explícitamente. El independent TEST queda congelado y cualquier acceso exige un registro auditable." },
]} />; }
