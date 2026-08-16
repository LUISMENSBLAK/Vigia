import Image from "next/image";
import Link from "next/link";

type LogoProps = { compact?: boolean; className?: string };

export function VigiaMark({ className = "" }: { className?: string }) {
  return (
    <Image
      src="/brand/vigia-logo.png"
      width={80}
      height={80}
      alt=""
      aria-hidden="true"
      priority
      className={className}
    />
  );
}

export function VigiaLogo({ compact = false, className = "" }: LogoProps) {
  return (
    <Link href="/" className={`brand-lockup ${className}`} aria-label="VIGÍA, inicio">
      <VigiaMark className="brand-mark" />
      {!compact && (
        <span>
          <strong>VIGÍA</strong>
          <small>Inteligencia geoespacial</small>
        </span>
      )}
    </Link>
  );
}
