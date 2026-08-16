import { SciencePage } from "@/components/science-page";

export default function ModelsPage() { return <SciencePage eyebrow="REGISTRO DE MODELOS" title="Versiones, datasets y límites visibles." introduction="Ningún modelo se considera publicable sin artefacto versionado, hash, configuración, seed y ejecución reproducible." notice="No hay modelos entrenados ni métricas publicadas." sections={[
  { title: "Risk Engine", body: "Comenzará con un baseline interpretable y calibrado antes de comparar modelos más complejos." },
  { title: "Detection Engine", body: "Requerirá incendios, negativos y falsos hotspots etiquetados; no se entrenará solo con positivos." },
  { title: "Spread Engine", body: "Será experimental y probabilístico, con ensembles P10/P50/P90 y advertencia operativa explícita." },
]} />; }
