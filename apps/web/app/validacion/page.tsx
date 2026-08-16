import { SciencePage } from "@/components/science-page";

export const metadata = { title: "Validación científica" };
export default function ValidationPage() {
  return <SciencePage eyebrow="VALIDACIÓN CIENTÍFICA" title="Resultados que puedan reproducirse o no se publican." introduction="La evaluación separará entrenamiento, validación y prueba, con divisiones temporales y espaciales que impidan fuga de información." notice="Validación en preparación. No existen métricas publicables ni casos evaluados todavía." sections={[
    { title: "Detección", body: "Precision, recall, F1, PR-AUC, tasa de falsos positivos y matriz de confusión, siempre con tamaño de muestra e intervalo." },
    { title: "Calibración", body: "Brier Score, curva de calibración y Expected Calibration Error cuando el conjunto permita estimarlos con rigor." },
    { title: "Tiempo y espacio", body: "Latencia hasta primera señal y alerta, error de localización, P90/P95 y comparación con perímetros observados." },
  ]} />;
}
