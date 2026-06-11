"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getPage } from "@/lib/api";
import { sanitizeCmsHtml } from "@/lib/sanitize";
import type { CmsPage } from "@/lib/types";

export default function CmsPageView() {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState<CmsPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!slug) return;
    getPage(slug)
      .then((r) => setPage(r.data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <p className="text-gray-500">Laden…</p>;
  if (notFound || !page) return <p className="text-red-600">Pagina niet gevonden.</p>;

  return (
    <div>
      <h1 className="text-3xl font-bold text-blue-800 mb-8">{page.title}</h1>
      <div
        className="cms-content"
        dangerouslySetInnerHTML={{ __html: sanitizeCmsHtml(page.content || "") }}
      />
    </div>
  );
}
