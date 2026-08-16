import { SciencePage } from "@/components/science-page";

export default function TransparencyPage() { return <SciencePage eyebrow="TRANSPARENCIA DE IA" title="Cómo obtuvo VIGÍA este resultado." introduction="Cada predicción futura podrá abrir su ficha de procedencia, modelo, variables, calidad, incertidumbre y actualización." sections={[
  { title: "Gobernanza", body: "Datasets, transformaciones, versiones y supervisión humana formarán parte del registro auditable." },
  { title: "Limitaciones", body: "Las ausencias de evidencia, cobertura, resolución y validación se mostrarán junto al resultado." },
  { title: "AI Act", body: "La arquitectura prepara documentación y trazabilidad sin afirmar una clasificación jurídica antes de un análisis legal." },
]} />; }
