import { SciencePage } from "@/components/science-page";

export default function ReplayPage() { return <SciencePage eyebrow="VIGÍA REPLAY" title="Evaluar el pasado sin mirar el futuro." introduction="Durante un replay, el motor solo podrá acceder a información con timestamp anterior o igual al reloj de reproducción." notice="Replay histórico en preparación. No hay casos publicados." sections={[
  { title: "Reloj controlado", body: "Play, pausa, velocidades y slider temporal harán avanzar la evidencia disponible sin data leakage." },
  { title: "Predicción", body: "Cada ejecución guardará modelo, dataset, commit, seed, parámetros y tiempo de replay." },
  { title: "Realidad observada", body: "Los resultados se compararán con perímetros y tiempos históricos, manteniendo separados ambos planos." },
]} />; }
