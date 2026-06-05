"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getPages } from "@/lib/api";
import type { CmsPage } from "@/lib/types";

export default function Navigation() {
  const [pages, setPages] = useState<CmsPage[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    getPages().then((r) => setPages(r.data)).catch(() => {});
  }, []);

  return (
    <nav style={{ backgroundColor: "var(--color-ocean-blue)" }} className="text-white shadow-md sticky top-0 z-50">
      <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
        <div>
          <Link href="/" className="hover:opacity-80">
            <span
              className="block font-bold tracking-tight leading-none"
              style={{ color: "var(--color-white)", fontSize: "2rem" }}
            >
              Raak
            </span>
            <span
              className="block text-sm font-medium"
              style={{ color: "var(--color-golden-yellow)" }}
            >
              Beleef meer in Millegem
            </span>
          </Link>
        </div>
        <button
          className="md:hidden p-2 rounded hover:opacity-80"
          onClick={() => setMenuOpen((o) => !o)}
          aria-label="Menu"
        >
          <span className="block w-6 h-0.5 bg-white mb-1" />
          <span className="block w-6 h-0.5 bg-white mb-1" />
          <span className="block w-6 h-0.5 bg-white" />
        </button>
        <ul
          className={`${menuOpen ? "flex" : "hidden"} md:flex flex-col md:flex-row gap-1 md:gap-2 absolute md:static top-16 left-0 right-0 p-4 md:p-0 z-50`}
          style={menuOpen ? { backgroundColor: "var(--color-ocean-blue)" } : {}}
        >
          <li><Link href="/" className="block px-3 py-2 rounded hover:opacity-80 font-medium">Home</Link></li>
          {pages.map((p) => (
            <li key={p.id}>
              <Link href={`/${p.slug}`} className="block px-3 py-2 rounded hover:opacity-80 font-medium">
                {p.title}
              </Link>
            </li>
          ))}
          <li><Link href="/archief" className="block px-3 py-2 rounded hover:opacity-80 font-medium">Archief</Link></li>
        </ul>
      </div>
    </nav>
  );
}
