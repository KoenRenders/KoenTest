import type { MetadataRoute } from "next";

// robots.txt (#300). Privé/niet-SEO-paden worden geweerd; de sitemap wordt
// aangewezen zodra de canonieke origin bekend is (NEXT_PUBLIC_SITE_URL, #301).
const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "").replace(/\/+$/, "");

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/admin", "/leden", "/login", "/betaling"],
    },
    ...(SITE_URL ? { sitemap: `${SITE_URL}/sitemap.xml`, host: SITE_URL } : {}),
  };
}
