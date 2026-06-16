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

export const metadata: Metadata = {
  title: `${ENV_PREFIX}Raak Millegem`,
  description: "De website van vereniging Raak Millegem",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="nl">
      <body className="font-primary">
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
