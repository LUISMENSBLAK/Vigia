import { SiteHeader } from "./site-header";

interface SciencePageProps {
  eyebrow: string;
  title: string;
  introduction: string;
  sections: Array<{ title: string; body: string }>;
  notice?: string;
}

export function SciencePage({ eyebrow, title, introduction, sections, notice }: SciencePageProps) {
  return (
    <>
      <SiteHeader />
      <main className="science-page">
        <header className="science-page__header">
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p>{introduction}</p>
        </header>
        {notice && <div className="science-notice" role="status"><strong>Estado actual</strong><span>{notice}</span></div>}
        <div className="science-sections">
          {sections.map((section, index) => (
            <section key={section.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div><h2>{section.title}</h2><p>{section.body}</p></div>
            </section>
          ))}
        </div>
      </main>
    </>
  );
}
