import type { MetadataRoute } from "next";
import { buildSitemapUrls } from "@/lib/sitemap";

// sitemap.xml (#300). De canonieke origin komt uit NEXT_PUBLIC_SITE_URL (#301).
// De gepubliceerde CMS-pagina's worden server-side opgehaald bij de backend
// (`/pages` filtert al is_published). De fetch gaat over het Docker-netwerk
// rechtstreeks naar de backend; INTERNAL_API_URL is overschrijfbaar maar valt
// terug op de servicenaam zodat geen extra env-wiring nodig is.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "";
const API = (process.env.INTERNAL_API_URL || "http://backend:8000").replace(/\/+$/, "");

// Sitemap hooguit elk uur herbouwen (ISR) — een nieuwe CMS-pagina verschijnt
// dan binnen het uur, zonder elke crawl de backend te laten raken.
export const revalidate = 3600;

async function fetchPublishedSlugs(): Promise<string[]> {
  try {
    const res = await fetch(`${API}/api/v1/pages`, { next: { revalidate } });
    if (!res.ok) return [];
    const pages = await res.json();
    if (!Array.isArray(pages)) return [];
    return pages.map((p: { slug?: string }) => p.slug).filter((s): s is string => !!s);
  } catch {
    // Backend onbereikbaar (bv. lokale `next dev` zonder stack): enkel de
    // vaste publieke routes in de sitemap, geen harde fout.
    return [];
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const slugs = await fetchPublishedSlugs();
  const now = new Date();
  return buildSitemapUrls(SITE_URL, slugs).map((url) => ({
    url,
    lastModified: now,
    changeFrequency: "weekly" as const,
    priority: url === `${SITE_URL.replace(/\/+$/, "")}/` ? 1 : 0.7,
  }));
}
