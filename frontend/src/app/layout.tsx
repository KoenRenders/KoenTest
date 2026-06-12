import type { Metadata } from "next";
import "./globals.css";
import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "Raak Millegem",
  description: "De website van vereniging Raak Millegem",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="nl">
      <body className="font-primary">
        <Navigation />
        <main className="max-w-7xl mx-auto px-4 py-8">
          {children}
        </main>
        <div className="max-w-7xl mx-auto px-4">
          <Footer />
        </div>
      </body>
    </html>
  );
}
