import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"),
  title: { default: "VIGÍA · Inteligencia satelital", template: "%s · VIGÍA" },
  description: "Sistema español de investigación geoespacial para incendios forestales.",
  icons: { icon: "/brand/vigia-logo.png", apple: "/brand/vigia-logo.png" },
  openGraph: { images: ["/brand/vigia-logo.png"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
