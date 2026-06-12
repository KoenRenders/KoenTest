"use client";
import { useEffect, useState } from "react";
import { getBlock } from "@/lib/api";
import { sanitizeCmsHtml } from "@/lib/sanitize";
import type { CmsPage } from "@/lib/types";

export default function Footer() {
  const [block, setBlock] = useState<CmsPage | null>(null);

  useEffect(() => {
    getBlock("site-footer").then((r) => setBlock(r.data)).catch(() => {});
  }, []);

  const year = new Date().getFullYear();

  return (
    <footer className="mt-16 border-t border-gray-200 pt-10 pb-6">
      {/* Sociale media */}
      <div className="flex justify-center gap-5 mb-6">
        <a
          href="https://www.facebook.com/raakmillegem"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Facebook"
          className="text-gray-500 hover:text-blue-700 transition-colors"
        >
          {/* Facebook */}
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-8 h-8">
            <path d="M22 12c0-5.523-4.477-10-10-10S2 6.477 2 12c0 4.991 3.657 9.128 8.438 9.878v-6.987H7.898V12h2.54V9.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V12h2.773l-.443 2.89h-2.33v6.988C18.343 21.128 22 16.991 22 12z" />
          </svg>
        </a>
        <a
          href="https://www.instagram.com/raakmillegem"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Instagram"
          className="text-gray-500 hover:text-pink-600 transition-colors"
        >
          {/* Instagram */}
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-8 h-8">
            <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z" />
          </svg>
        </a>
        <a
          href="https://www.tiktok.com/@raakmillegem"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="TikTok"
          className="text-gray-500 hover:text-black transition-colors"
        >
          {/* TikTok */}
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-8 h-8">
            <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 00-.79-.05 6.34 6.34 0 00-6.34 6.34 6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.33-6.34V9a8.17 8.17 0 004.78 1.52V7.07a4.85 4.85 0 01-1.01-.38z" />
          </svg>
        </a>
      </div>

      {/* Sponsor Mona */}
      <div className="flex justify-center mb-6">
        <div className="text-center">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Met steun van</p>
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-gray-50 rounded-lg border border-gray-100">
            <span className="font-bold text-lg tracking-wide text-teal-600">mona</span>
            <span className="text-xs text-gray-500 italic">Samen veilig naar onze toekomst</span>
          </div>
        </div>
      </div>

      {/* CMS-inhoud (verenigingsinfo) */}
      {block?.content ? (
        <div
          className="cms-content text-center text-sm text-gray-500 mb-4"
          dangerouslySetInnerHTML={{ __html: sanitizeCmsHtml(block.content) }}
        />
      ) : (
        <p className="text-center text-sm text-gray-500 mb-4">
          Feitelijke vereniging Raak Millegem · Milostraat 40, 2400 Mol ·{" "}
          <a href="mailto:raakmillegem@gmail.com" className="hover:underline">raakmillegem@gmail.com</a>
          {" "}· IBAN: BE48 7875 5016 1327 · BIC: GKCCBEBB
        </p>
      )}

      <p className="text-center text-xs text-gray-400">
        © {year} Raak Millegem
      </p>
    </footer>
  );
}
