import type { Metadata } from "next";
import { Radio_Canada_Big } from "next/font/google";
import "./globals.css";
import Navigation from "@/components/Navigation";

const radioCanadaBig = Radio_Canada_Big({
  subsets: ["latin"],
  variable: "--font-radio-canada-big",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Raak Millegem",
  description: "De website van vereniging Raak Millegem",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="nl">
      <body className={`${radioCanadaBig.variable} font-primary`}>
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
