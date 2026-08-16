import { SciencePage } from "@/components/science-page";

export default function AccessibilityPage() { return <SciencePage eyebrow="ACCESIBILIDAD" title="Información crítica más allá del mapa." introduction="El objetivo mínimo es EN 301 549 v3.2.1 y WCAG 2.1 AA, aplicando WCAG 2.2 AA cuando sea posible." sections={[
  { title: "Alternativas textuales", body: "Incidentes, estados, evidencias y alertas tendrán listas y fichas semánticas equivalentes." },
  { title: "Interacción", body: "Teclado, foco visible, reduced motion, contraste, labels y lectores de pantalla forman parte del criterio de terminado." },
  { title: "Evaluación", body: "Las auditorías automáticas y manuales se documentarán con versión y fecha; no se declara conformidad todavía." },
]} />; }
