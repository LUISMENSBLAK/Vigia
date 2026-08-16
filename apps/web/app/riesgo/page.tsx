import { SciencePage } from "@/components/science-page";

export default function RiskPage() { return <SciencePage eyebrow="VIGÍA RISK ENGINE" title="Condiciones de riesgo, separadas de la presencia de fuego." introduction="El riesgo estima si las condiciones permiten una ignición; no afirma que exista un incendio activo." notice="Motor baseline en preparación. No hay superficies de riesgo publicadas." sections={[
  { title: "Meteorología", body: "Temperatura, humedad, viento, rachas, precipitación y edad de cada observación." },
  { title: "Terreno y combustible", body: "Vegetación, humedad, pendiente, orientación, elevación y continuidad vegetal con CRS explícito." },
  { title: "Explicabilidad", body: "Versión de modelo, intervalo de confianza, factores principales y calidad de entrada acompañarán cada resultado." },
]} />; }
