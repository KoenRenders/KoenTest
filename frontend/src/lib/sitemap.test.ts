import { describe, it, expect } from "vitest";
import { buildSitemapPaths, buildSitemapUrls, STATIC_PATHS } from "@/lib/sitemap";

describe("buildSitemapPaths", () => {
  it("bevat altijd de vaste publieke routes", () => {
    const paths = buildSitemapPaths([]);
    for (const p of STATIC_PATHS) expect(paths).toContain(p);
  });

  it("prefixt CMS-slugs met / en negeert lege/whitespace", () => {
    const paths = buildSitemapPaths(["over-ons", "", "  ", "contact"]);
    expect(paths).toContain("/over-ons");
    expect(paths).toContain("/contact");
    expect(paths).not.toContain("/ ");  // lege/whitespace-slug levert geen pad op
  });

  it("voegt geen dubbele paden toe", () => {
    const paths = buildSitemapPaths(["archief"]); // /archief is al statisch
    expect(paths.filter((p) => p === "/archief")).toHaveLength(1);
  });

  it("dwingt geen admin/leden-paden af (komen niet uit gepubliceerde CMS-slugs)", () => {
    const paths = buildSitemapPaths(["over-ons"]);
    expect(paths.some((p) => p.startsWith("/admin"))).toBe(false);
    expect(paths.some((p) => p.startsWith("/leden"))).toBe(false);
  });
});

describe("buildSitemapUrls", () => {
  it("maakt absolute URL's t.o.v. de site-origin", () => {
    const urls = buildSitemapUrls("https://raak.example", ["over-ons"]);
    expect(urls).toContain("https://raak.example/");
    expect(urls).toContain("https://raak.example/over-ons");
  });

  it("negeert een trailing slash op de origin", () => {
    const urls = buildSitemapUrls("https://raak.example/", ["contact"]);
    expect(urls).toContain("https://raak.example/contact");
    expect(urls.some((u) => u.includes("//contact"))).toBe(false);
  });
});
