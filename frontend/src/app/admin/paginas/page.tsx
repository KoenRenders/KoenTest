"use client";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { getPages, createPage, updatePage, deletePage } from "@/lib/api";
import type { CmsPage } from "@/lib/types";

const emptyPage = () => ({ title: "", slug: "", content: "", is_published: false, sort_order: 0 });

export default function AdminPaginas() {
  const [pages, setPages] = useState<CmsPage[]>([]);
  const [form, setForm] = useState(emptyPage());
  const [editing, setEditing] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [preview, setPreview] = useState(false);

  function load() {
    getPages().then((r) => setPages(r.data)).catch(() => {});
  }

  useEffect(() => { load(); }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (editing !== null) {
      await updatePage(editing, form);
    } else {
      await createPage(form);
    }
    setShowForm(false);
    setEditing(null);
    setForm(emptyPage());
    load();
  }

  function startEdit(p: CmsPage) {
    setForm({ title: p.title, slug: p.slug, content: p.content || "", is_published: p.is_published, sort_order: p.sort_order });
    setEditing(p.id);
    setShowForm(true);
    setPreview(false);
  }

  async function handleDelete(id: number) {
    if (!confirm("Verwijder deze pagina?")) return;
    await deletePage(id);
    load();
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-blue-800">CMS Pagina's</h1>
        <button className="btn-primary btn-sm" onClick={() => { setShowForm(true); setEditing(null); setForm(emptyPage()); setPreview(false); }}>
          + Nieuwe pagina
        </button>
      </div>

      {showForm && (
        <div className="card mb-6">
          <h2 className="font-bold text-lg mb-4">{editing !== null ? "Pagina bewerken" : "Nieuwe pagina"}</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="label">Titel *</label>
                <input className="input" required value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
              </div>
              <div>
                <label className="label">Slug *</label>
                <input className="input" required value={form.slug} placeholder="bijv. werking" onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))} />
              </div>
              <div>
                <label className="label">Volgorde</label>
                <input type="number" className="input" value={form.sort_order} onChange={(e) => setForm((f) => ({ ...f, sort_order: parseInt(e.target.value) }))} />
              </div>
              <div className="flex items-center gap-2 pt-6">
                <input type="checkbox" id="published" checked={form.is_published} onChange={(e) => setForm((f) => ({ ...f, is_published: e.target.checked }))} />
                <label htmlFor="published">Gepubliceerd</label>
              </div>
            </div>

            {/* Editor / Preview toggle */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="label mb-0">Inhoud (Markdown)</label>
                <button
                  type="button"
                  className="text-xs text-blue-600 hover:underline"
                  onClick={() => setPreview((p) => !p)}
                >
                  {preview ? "← Bewerken" : "Voorbeeld →"}
                </button>
              </div>

              {preview ? (
                <div className="border border-gray-200 rounded-lg p-4 min-h-[300px] bg-white prose prose-sm max-w-none">
                  <ReactMarkdown>{form.content}</ReactMarkdown>
                </div>
              ) : (
                <textarea
                  className="input font-mono text-sm min-h-[300px]"
                  value={form.content}
                  onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
                  placeholder={"## Titel\n\nTekst hier…\n\n- Punt 1\n- Punt 2"}
                />
              )}
              <p className="text-xs text-gray-400 mt-1">Markdown: ## kop, **vet**, *cursief*, - lijst, [link](url)</p>
            </div>

            <div className="flex gap-3">
              <button type="submit" className="btn-primary">Opslaan</button>
              <button type="button" className="btn-secondary" onClick={() => { setShowForm(false); setEditing(null); }}>Annuleren</button>
            </div>
          </form>
        </div>
      )}

      <div className="space-y-3">
        {pages.map((p) => (
          <div key={p.id} className="card flex items-center justify-between gap-4">
            <div>
              <span className="font-semibold">{p.title}</span>
              <span className="ml-2 text-sm text-gray-500">/{p.slug}</span>
              {!p.is_published && <span className="ml-2 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">Concept</span>}
            </div>
            <div className="flex gap-2">
              <button className="btn-secondary btn-sm" onClick={() => startEdit(p)}>Bewerken</button>
              <button className="btn-danger btn-sm" onClick={() => handleDelete(p.id)}>Verwijderen</button>
            </div>
          </div>
        ))}
        {pages.length === 0 && <p className="text-gray-500 text-sm">Geen pagina's.</p>}
      </div>
    </div>
  );
}
