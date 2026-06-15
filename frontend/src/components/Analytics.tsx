"use client";
import Script from "next/script";
import { usePathname } from "next/navigation";

// Cookieloze, zelf-gehoste web-analytics via Umami (#152, laag 1).
// - Laadt enkel op de PUBLIEKE site: nooit op /admin of /login.
// - Laadt enkel wanneer geconfigureerd (src + website-id via NEXT_PUBLIC_*),
//   dus lokaal/dev is dit een no-op.
// - data-do-not-track="true" laat Umami de browser-DNT respecteren.
const SRC = process.env.NEXT_PUBLIC_UMAMI_SRC;
const WEBSITE_ID = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID;

export default function Analytics() {
  const pathname = usePathname();
  if (!SRC || !WEBSITE_ID) return null;
  if (pathname?.startsWith("/admin") || pathname?.startsWith("/login")) return null;
  return (
    <Script
      src={SRC}
      data-website-id={WEBSITE_ID}
      data-do-not-track="true"
      strategy="afterInteractive"
    />
  );
}
