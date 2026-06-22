import type { Metadata } from "next";
import "./globals.css";
import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import EnvBar from "@/components/EnvBar";
import Analytics from "@/components/Analytics";
import ChatWidget from "@/components/ChatWidget";

// Omgevingsindicator (#145): op niet-PROD prefixen we de tab-titel met
// [HDEV]/[UAT]/[DEV]. Op PROD (of zonder waarde) blijft het "Raak Millegem".
const APP_ENV = (process.env.NEXT_PUBLIC_APP_ENV || "").toLowerCase();
const ENV_PREFIX = APP_ENV && APP_ENV !== "prod" ? `[${APP_ENV.toUpperCase()}] ` : "";

// Canonieke publieke origin (#301): geen echte domeinnaam in git → uit de env
// (afgeleid van FRONTEND_URL per omgeving). Maakt OG/canonical/sitemap absoluut.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "";
const SITE_NAME = "Raak Millegem";
const DESCRIPTION = "De website van Raak Millegem";

export const metadata: Metadata = {
  metadataBase: SITE_URL ? new URL(SITE_URL) : undefined,
  title: { default: `${ENV_PREFIX}${SITE_NAME}`, template: `${ENV_PREFIX}%s — ${SITE_NAME}` },
  description: DESCRIPTION,
  applicationName: SITE_NAME,
  icons: { icon: "/logo.png" },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    locale: "nl_BE",
    title: SITE_NAME,
    description: DESCRIPTION,
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: SITE_NAME }],
    ...(SITE_URL ? { url: SITE_URL } : {}),
  },
  twitter: { card: "summary_large_image", title: SITE_NAME, description: DESCRIPTION, images: ["/og-image.png"] },
};

// Organization-structured-data (#302): helpt Google/Bing de vereniging herkennen.
// sameAs (sociale media) kan later toegevoegd worden.
const orgJsonLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: SITE_NAME,
  description: DESCRIPTION,
  ...(SITE_URL ? { url: SITE_URL, logo: `${SITE_URL}/logo.png` } : {}),
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="nl">
      <body className="font-primary">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(orgJsonLd) }}
        />
        <Analytics />
        <header className="sticky top-0 z-50">
          <EnvBar />
          <Navigation />
        </header>
        <main className="max-w-7xl mx-auto px-4 py-8">
          {children}
        </main>
        <div className="max-w-7xl mx-auto px-4">
          <Footer />
        </div>
        <ChatWidget />
      </body>
    </html>
  );
}
