import type { Metadata } from "next";
import { Nunito } from "next/font/google";
import "./globals.css";
import Navigation from "@/components/Navigation";

const nunito = Nunito({
  subsets: ["latin"],
  variable: "--font-primary",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Raak Millegem",
  description: "De website van vereniging Raak Millegem",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="nl">
      <body className={`${nunito.variable} font-primary`}>
        <Navigation />
        <main className="max-w-5xl mx-auto px-4 py-8">
          {children}
        </main>
        <footer className="mt-16 border-t border-gray-200 py-6 text-center text-sm text-gray-500">
          © {new Date().getFullYear()} Raak Millegem · raakmillegem@gmail.com
        </footer>
      </body>
    </html>
  );
}
