import { SciencePage } from "@/components/science-page";

export default function SourcesPage() { return <SciencePage eyebrow="FUENTES Y CALIDAD" title="Cada fuente conserva sus límites." introduction="VIGÍA mostrará latencia, cobertura, resolución, calidad y disponibilidad sin utilizar la expresión tiempo real para datos retrasados." sections={[
  { title: "Satélite", body: "EUMETSAT MTG FCI, NASA FIRMS y Copernicus Sentinel se procesan en workers independientes." },
  { title: "Meteorología", body: "AEMET distinguirá valores observados, interpolados y pronosticados." },
  { title: "Terreno", body: "PNOA LiDAR y CNIG aportarán productos derivados; los archivos pesados permanecerán fuera de PostgreSQL." },
]} />; }
