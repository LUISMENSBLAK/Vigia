import Link from "next/link";

import { SiteHeader } from "@/components/site-header";
import { VigiaMark } from "@/components/vigia-logo";

const pillars = [
  ["Observación", "MTG, Sentinel, VIIRS y MODIS con procedencia y latencia explícitas."],
  ["Fusión", "Evidencias independientes, calidad de dato y contradicciones conservadas."],
  ["Validación", "Separación temporal y espacial; métricas solo desde ejecuciones reproducibles."],
];

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main>
        <section className="hero">
          <div className="hero__grid">
            <div className="hero__copy">
              <p className="eyebrow">SISTEMA ESPAÑOL DE INTELIGENCIA GEOESPACIAL</p>
              <h1>Inteligencia satelital para anticiparnos al fuego.</h1>
              <p className="hero__lead">Sistema español de inteligencia geoespacial que combina observación satelital, meteorología, información forestal e inteligencia artificial para investigar nuevas formas de prevenir, detectar y predecir incendios forestales.</p>
              <div className="hero__actions">
                <Link className="button button--primary" href="/mapa">Explorar VIGÍA</Link>
                <Link className="button button--secondary" href="/validacion">Ver validación</Link>
              </div>
              <p className="research-note">Proyecto en fase de investigación. No es un sistema operativo de emergencias.</p>
            </div>
            <div className="hero__visual" aria-hidden="true">
              <div className="orbital-rings"><VigiaMark className="hero-mark" /></div>
              <span className="coordinate coordinate--one">40.6566° N · 4.6812° W</span>
              <span className="coordinate coordinate--two">ÁVILA · ÁREA PRIORITARIA</span>
            </div>
          </div>
        </section>

        <section className="mission">
          <p className="eyebrow">UNA INFRAESTRUCTURA PARA SER INSPECCIONADA</p>
          <div className="mission__intro">
            <h2>Datos reales. Trazabilidad completa. Incertidumbre visible.</h2>
            <p>VIGÍA separa estrictamente riesgo, observación, detección, confianza y propagación. Ninguna probabilidad alta se convierte por sí sola en un incendio confirmado.</p>
          </div>
          <div className="pillar-grid">
            {pillars.map(([title, description], index) => (
              <article key={title}><span>0{index + 1}</span><h3>{title}</h3><p>{description}</p></article>
            ))}
          </div>
        </section>

        <section className="pipeline">
          <div><p className="eyebrow">ARQUITECTURA ABIERTA</p><h2>De la señal al resultado reproducible.</h2></div>
          <ol>
            {[
              ["01", "Satélite", "Observaciones con timestamp y calidad"],
              ["02", "Fusión", "Acuerdo, contradicción y evidencia faltante"],
              ["03", "IA", "Modelos versionados y calibrados"],
              ["04", "Validación", "Resultados auditables, nunca decorativos"],
            ].map(([number, title, body]) => <li key={number}><span>{number}</span><strong>{title}</strong><small>{body}</small></li>)}
          </ol>
        </section>
      </main>
      <footer className="site-footer"><span>VIGÍA · España</span><span>Investigación responsable para la resiliencia forestal europea</span></footer>
    </>
  );
}
