// Pure URL-bouw voor de sitemap (#300). Losgekoppeld van de Next-route zodat de
// invarianten testbaar zijn (Vitest): geen admin/leden-paden, CMS-slugs correct
// geprefixt, absoluut t.o.v. de site-origin, gededupliceerd. De vraag "welke
// pagina's zijn publiek/gepubliceerd" zit backend-side (`/pages` filtert
// is_published) — hier mappen we enkel die al-gefilterde slugs naar URL's.

// Vaste publieke routes die altijd in de sitemap horen.
export const STATIC_PATHS = ["/", "/archief"] as const;

/** Maak een genormaliseerde, gededupliceerde lijst paden uit de CMS-slugs. */
export function buildSitemapPaths(slugs: string[]): string[] {
  const cms = slugs
    .filter((s) => typeof s === "string" && s.trim().length > 0)
    .map((s) => `/${s.trim().replace(/^\/+/, "")}`);
  return Array.from(new Set<string>([...STATIC_PATHS, ...cms]));
}

/** Absolute sitemap-URL's t.o.v. de site-origin (trailing slash genegeerd). */
export function buildSitemapUrls(siteUrl: string, slugs: string[]): string[] {
  const base = siteUrl.replace(/\/+$/, "");
  return buildSitemapPaths(slugs).map((p) => `${base}${p}`);
}
