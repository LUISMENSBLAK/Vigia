import { SciencePage } from "@/components/science-page";

export default function PrivacyPage() { return <SciencePage eyebrow="PRIVACIDAD" title="Minimización desde el diseño." introduction="VIGÍA no necesita perfiles publicitarios ni datos personales para mostrar información forestal y geoespacial pública." sections={[
  { title: "Datos personales", body: "No se recopilarán datos personales que no resulten estrictamente necesarios para una función autorizada." },
  { title: "Telemetría", body: "No se incorporan trackers publicitarios. Cualquier observabilidad futura deberá documentarse y minimizarse." },
  { title: "Retención", body: "Las políticas de conservación, finalidad y derechos se definirán antes de procesar información personal." },
]} />; }
