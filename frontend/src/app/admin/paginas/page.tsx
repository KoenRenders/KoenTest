"use client";
import { useEffect, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import { getAllPages, createPage, updatePage, deletePage } from "@/lib/api";
import type { CmsPage } from "@/lib/types";

const emptyPage = () => ({ title: "", slug: "", content: "", is_published: false, sort_order: 0 });

function MenuBar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null;
  const btn = (active: boolean) =>
    `px-2 py-1 rounded text-sm border transition-colors ${active ? "bg-blue-700 text-white border-blue-700" : "bg-white border-gray-300 hover:bg-gray-100"}`;
  return (
    <div className="flex flex-wrap gap-1 border border-gray-300 border-b-0 rounded-t-lg bg-gray-50 px-2 py-2">
      <button type="button" className={btn(editor.isActive("bold"))} onClick={() => editor.chain().focus().toggleBold().run()}>V</button>
      <button type="button" className={btn(editor.isActive("italic"))} onClick={() => editor.chain().focus().toggleItalic().run()}>S</button>
      <button type="button" className={btn(editor.isActive("heading", { level: 2 }))} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}>H2</button>
      <button type="button" className={btn(editor.isActive("heading", { level: 3 }))} onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}>H3</button>
      <button type="button" className={btn(editor.isActive("bulletList"))} onClick={() => editor.chain().focus().toggleBulletList().run()}>• lijst</button>
      <button type="button" className={btn(editor.isActive("orderedList"))} onClick={() => editor.chain().focus().toggleOrderedList().run()}>1. lijst</button>
      <button type="button" className={btn(editor.isActive("blockquote"))} onClick={() => editor.chain().focus().toggleBlockquote().run()}>❝</button>
      <button type="button" className={btn(false)} onClick={() => editor.chain().focus().setHorizontalRule().run()}>—</button>
      <button
        type="button"
        className={btn(editor.isActive("link"))}
        onClick={() => {
          if (editor.isActive("link")) { editor.chain().focus().unsetLink().run(); return; }
          const url = window.prompt("URL:");
          if (url) editor.chain().focus().setLink({ href: url }).run();
        }}
      >
        🔗
      </button>
      <button type="button" className={btn(false)} onClick={() => editor.chain().focus().undo().run()}>↩</button>
      <button type="button" className={btn(false)} onClick={() => editor.chain().focus().redo().run()}>↪</button>
    </div>
  );
}

function RichEditor({ value, onChange }: { value: string; onChange: (html: string) => void }) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Link.configure({ openOnClick: false }),
    ],
    content: value,
    onUpdate: ({ editor }) => onChange(editor.getHTML()),
  });

  useEffect(() => {
    if (editor && value !== editor.getHTML()) {
      editor.commands.setContent(value, false);
    }
  }, [value, editor]);

  return (
    <div>
      <MenuBar editor={editor} />
      <EditorContent
        editor={editor}
        className="border border-gray-300 rounded-b-lg bg-white min-h-[300px] px-4 py-3 focus-within:ring-2 focus-within:ring-blue-500 cms-editor"
      />
    </div>
  );
}

export default function AdminPaginas() {
  const [pages, setPages] = useState<CmsPage[]>([]);
  const [form, setForm] = useState(emptyPage());
  const [editing, setEditing] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);

  function load() {
    getAllPages().then((r) => setPages(r.data)).catch(() => {});
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
        <button className="btn-primary btn-sm" onClick={() => { setShowForm(true); setEditing(null); setForm(emptyPage()); }}>
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

            <div>
              <label className="label">Inhoud</label>
              <RichEditor value={form.content} onChange={(html) => setForm((f) => ({ ...f, content: html }))} />
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
