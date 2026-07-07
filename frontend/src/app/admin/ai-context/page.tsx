"use client";
import { useEffect, useState } from "react";
import {
  getChatbotInfo,
  upsertMediaChatbotInfo,
  upsertCmsChatbotInfo,
  createChatbotNote,
  updateChatbotRow,
  deleteChatbotRow,
  reextractMedia,
  type ChatbotInfoData,
  type ChatbotInfoRow,
} from "@/lib/api";
import { parseApiError } from "@/lib/errors";

// 'Raakje — AI-context' (#235, #375): beheer van alles wat naar de chatbot gaat
// (chatbot_info). Drie gegroepeerde en gerangschikte lijsten (① documenten,
// ② CMS-pagina's, ③ vrije notities), telkens met een "Bewerken"-knop per rij —
// zoals de CMS-pagina's.

export default function AiContextPage() {
  const [data, setData] = useState<ChatbotInfoData | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  // Welk item wordt bewerkt: "doc:<asset_id>" | "cms:<page_id>" | "note:<id>" | "note:new".
  const [editing, setEditing] = useState<string | null>(null);

  async function load() {
    try {
      const r = await getChatbotInfo();
      setData(r.data);
    } catch (e) {
      setError(parseApiError(e, "Kon de AI-context niet laden."));
    }
  }
  useEffect(() => {
    load();
  }, []);

  const close = () => setEditing(null);
  async function reloadAndClose() {
    await load();
    close();
  }

  if (error) return <div className="text-red-600">{error}</div>;
  if (!data) return <div>Laden…</div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-blue-800">Raakje — AI-context</h1>
        <p className="text-gray-600 text-sm mt-1">
          Alles hieronder sturen we mee als context naar de chatbot. Datum, prijs en
          locatie komen altijd uit de structuurvelden en winnen van deze tekst.
        </p>
      </div>

      {notice && <div className="text-green-700 text-sm">{notice}</div>}

      <section>
        <h2 className="text-lg font-semibold mb-3">① Documenten (posters &amp; reglementen)</h2>
        {data.documents.length === 0 && (
          <p className="text-gray-500 text-sm">Nog geen posters of reglementen opgeladen.</p>
        )}
        <div className="space-y-2">
          {data.documents.map((d) => {
            const key = `doc:${d.asset_id}`;
            return editing === key ? (
              <DocumentCard key={key} doc={d} onDone={reloadAndClose} onClose={close} onNotice={setNotice} onReload={load} />
            ) : (
              <ListRow
                key={key}
                title={d.label}
                status={statusOf(d.info)}
                onEdit={() => setEditing(key)}
              />
            );
          })}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">② Website-pagina&apos;s (gaan standaard mee)</h2>
        <div className="space-y-2">
          {data.cms.map((p) => {
            const key = `cms:${p.page_id}`;
            return editing === key ? (
              <CmsCard key={key} page={p} onDone={reloadAndClose} onClose={close} />
            ) : (
              <ListRow
                key={key}
                title={p.title}
                status={statusOf(p.info)}
                onEdit={() => setEditing(key)}
              />
            );
          })}
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">③ Eigen AI-context (vrije notities)</h2>
          <button className="btn-primary btn-sm" onClick={() => setEditing("note:new")}>+ Nieuwe notitie</button>
        </div>
        <p className="text-gray-500 text-xs mb-3">
          Korte, stabiele info die nergens op de site staat (wie we zijn, vaste FAQ…).
          Geen prijzen/datums — die verouderen en komen uit de structuurvelden.
        </p>
        <div className="space-y-2">
          {editing === "note:new" && <NewNoteForm onDone={reloadAndClose} onClose={close} />}
          {data.notes.map((n) => {
            const key = `note:${n.id}`;
            return editing === key ? (
              <NoteCard key={key} note={n} onDone={reloadAndClose} onClose={close} />
            ) : (
              <ListRow
                key={key}
                title={n.title || "(zonder titel)"}
                status={n.is_active ? "mee naar Raakje" : "uit"}
                onEdit={() => setEditing(key)}
              />
            );
          })}
          {data.notes.length === 0 && editing !== "note:new" && (
            <p className="text-gray-500 text-sm">Nog geen notities.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function statusOf(info: ChatbotInfoRow | null | undefined): string {
  if (!info) return "standaard";
  if (info.is_active === false) return "uit";
  return info.text_override ? "aangepast" : "mee naar Raakje";
}

function ListRow({ title, status, onEdit }: { title: string; status: string; onEdit: () => void }) {
  return (
    <div className="card flex items-center justify-between gap-4 py-3">
      <div className="min-w-0">
        <span className="font-medium truncate">{title}</span>
        <span className="ml-2 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{status}</span>
      </div>
      <button className="btn-secondary btn-sm" onClick={onEdit}>Bewerken</button>
    </div>
  );
}

function EditorHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <span className="font-semibold">{title}</span>
      <button className="text-gray-500 hover:text-gray-800 text-sm" onClick={onClose}>Sluiten ✕</button>
    </div>
  );
}

function ActiveToggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function DocumentCard({
  doc,
  onReload,
  onDone,
  onClose,
  onNotice,
}: {
  doc: ChatbotInfoData["documents"][number];
  onReload: () => void;
  onDone: () => void;
  onClose: () => void;
  onNotice: (s: string) => void;
}) {
  const info = doc.info;
  const [override, setOverride] = useState(info?.text_override ?? "");
  const [addition, setAddition] = useState(info?.text_addition ?? "");
  const [active, setActive] = useState(info?.is_active ?? true);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await upsertMediaChatbotInfo(doc.asset_id, {
        text_override: override || null,
        text_addition: addition || null,
        is_active: active,
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }
  async function reread() {
    setBusy(true);
    try {
      await reextractMedia(doc.asset_id);
      onNotice("Raakje leest het document opnieuw. Herlaad over enkele tellen.");
      setTimeout(onReload, 3000);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <EditorHeader title={doc.label} onClose={onClose} />
      <div className="flex justify-end mb-2">
        <button className="btn-secondary btn-sm" onClick={reread} disabled={busy}>Opnieuw lezen</button>
      </div>
      <label className="label text-xs">Automatisch gelezen (machine)</label>
      <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-2 whitespace-pre-wrap max-h-40 overflow-auto mb-3">
        {info?.extracted_text || "(nog niets gelezen — gebruik 'Opnieuw lezen')"}
      </pre>
      <label className="label text-xs">Correctie (vervangt de machine-lezing)</label>
      <textarea className="input mb-2" rows={2} value={override} onChange={(e) => setOverride(e.target.value)} />
      <label className="label text-xs">Aanvulling (extra info, wordt toegevoegd)</label>
      <textarea className="input mb-2" rows={2} value={addition} onChange={(e) => setAddition(e.target.value)} />
      <div className="flex items-center justify-between">
        <ActiveToggle checked={active} onChange={setActive} label="Mee naar Raakje" />
        <button className="btn-primary btn-sm" onClick={save} disabled={busy}>Bewaar</button>
      </div>
    </div>
  );
}

function CmsCard({
  page,
  onDone,
  onClose,
}: {
  page: ChatbotInfoData["cms"][number];
  onDone: () => void;
  onClose: () => void;
}) {
  const info = page.info;
  const [override, setOverride] = useState(info?.text_override ?? "");
  const [addition, setAddition] = useState(info?.text_addition ?? "");
  const [active, setActive] = useState(info?.is_active ?? true);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await upsertCmsChatbotInfo(page.page_id, {
        text_override: override || null,
        text_addition: addition || null,
        is_active: active,
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }
  async function reset() {
    if (!info) return;
    setBusy(true);
    try {
      await deleteChatbotRow(info.id);
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <EditorHeader title={page.title} onClose={onClose} />
      <label className="label text-xs">Override (vervangt de pagina-inhoud voor de bot)</label>
      <textarea className="input mb-2" rows={2} value={override} onChange={(e) => setOverride(e.target.value)} placeholder="Leeg = de bot gebruikt de gewone pagina-inhoud" />
      <label className="label text-xs">Aanvulling (extra info voor de bot)</label>
      <textarea className="input mb-2" rows={2} value={addition} onChange={(e) => setAddition(e.target.value)} />
      <div className="flex items-center justify-between gap-2">
        <ActiveToggle checked={active} onChange={setActive} label="Mee naar Raakje" />
        <div className="flex items-center gap-2">
          {info && (
            <button className="btn-secondary btn-sm" onClick={reset} disabled={busy}>Herstel naar standaard</button>
          )}
          <button className="btn-primary btn-sm" onClick={save} disabled={busy}>Bewaar</button>
        </div>
      </div>
    </div>
  );
}

function NoteCard({ note, onDone, onClose }: { note: ChatbotInfoRow; onDone: () => void; onClose: () => void }) {
  const [title, setTitle] = useState(note.title ?? "");
  const [text, setText] = useState(note.text_addition ?? "");
  const [active, setActive] = useState(note.is_active);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await updateChatbotRow(note.id, {
        title: title || null,
        text_addition: text || null,
        text_override: null,
        is_active: active,
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!confirm("Deze notitie verwijderen?")) return;
    setBusy(true);
    try {
      await deleteChatbotRow(note.id);
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <EditorHeader title={note.title || "(zonder titel)"} onClose={onClose} />
      <input className="input mb-2" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Titel" />
      <textarea className="input mb-2" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="flex items-center justify-between">
        <ActiveToggle checked={active} onChange={setActive} label="Mee naar Raakje" />
        <div className="flex gap-2">
          <button className="btn-danger btn-sm" onClick={remove} disabled={busy}>Verwijder</button>
          <button className="btn-primary btn-sm" onClick={save} disabled={busy}>Bewaar</button>
        </div>
      </div>
    </div>
  );
}

function NewNoteForm({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function create() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await createChatbotNote({ title: title || null, text_addition: text, is_active: true });
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card border-dashed">
      <EditorHeader title="Nieuwe notitie" onClose={onClose} />
      <input className="input mb-2" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Titel (optioneel)" />
      <textarea className="input mb-2" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Wat moet Raakje weten?" />
      <div className="flex justify-end">
        <button className="btn-primary btn-sm" onClick={create} disabled={busy || !text.trim()}>Toevoegen</button>
      </div>
    </div>
  );
}
