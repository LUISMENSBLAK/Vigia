import Link from "next/link";

import { VigiaLogo } from "./vigia-logo";

const links = [
  ["Mapa", "/mapa"],
  ["Riesgo", "/riesgo"],
  ["Validación", "/validacion"],
  ["Metodología", "/metodologia"],
  ["Estado", "/estado"],
] as const;

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <VigiaLogo />
        <nav aria-label="Navegación principal">
          {links.map(([label, href]) => (
            <Link href={href} key={href}>{label}</Link>
          ))}
        </nav>
        <Link className="language" href="/en" aria-label="Cambiar idioma a inglés">ES / EN</Link>
      </div>
    </header>
  );
}
