"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { getPage } from "@/lib/api";
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
      <div className="space-y-4 text-gray-800 leading-relaxed">
        <ReactMarkdown components={{
          h2: ({children}) => <h2 className="text-2xl font-bold text-blue-800 mt-8 mb-3">{children}</h2>,
          h3: ({children}) => <h3 className="text-xl font-semibold text-blue-700 mt-6 mb-2">{children}</h3>,
          p: ({children}) => <p className="mb-3">{children}</p>,
          ul: ({children}) => <ul className="list-disc list-outside ml-6 mb-3 space-y-1">{children}</ul>,
          ol: ({children}) => <ol className="list-decimal list-outside ml-6 mb-3 space-y-1">{children}</ol>,
          li: ({children}) => <li>{children}</li>,
          a: ({href, children}) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{children}</a>,
          strong: ({children}) => <strong className="font-semibold">{children}</strong>,
        }}>{page.content || ""}</ReactMarkdown>
      </div>
    </div>
  );
}
