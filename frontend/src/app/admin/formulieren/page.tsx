"use client";
import { useEffect, useState } from "react";
import {
  getForms, getForm, createForm, updateForm, deleteForm, getFormResults, exportForm,
} from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import type { FormSummary, FormAdmin, FormFieldDef } from "@/lib/types";

const FIELD_TYPES: { value: string; label: string }[] = [
  { value: "text", label: "Korte tekst" },
  { value: "textarea", label: "Lange tekst" },
  { value: "number", label: "Getal" },
  { value: "email", label: "E-mail" },
  { value: "select", label: "Keuzelijst" },
  { value: "radio", label: "Eén keuze" },
  { value: "checkbox", label: "Meerkeuze" },
  { value: "rating", label: "Beoordeling (1–5)" },
];
const CHOICE_TYPES = ["select", "radio", "checkbox"];

type EditOption = { label: string; value: string; position: number };
type EditField = {
  field_type: string;
  label: string;
  help_text: string;
  required: boolean;
  position: number;
  min_value: string;
  max_value: string;
  min_length: string;
  max_length: string;
  regex_pattern: string;
  options: EditOption[];
};
type EditForm = {
  id?: number;
  title: string;
  description: string;
  status: string;
  max_submissions: string;
  send_confirmation: boolean;
  confirmation_message: string;
  allow_edit: boolean;
  share_token?: string;
  fields: EditField[];
};

function emptyField(): EditField {
  return {
    field_type: "text", label: "", help_text: "", required: false, position: 0,
    min_value: "", max_value: "", min_length: "", max_length: "", regex_pattern: "", options: [],
  };
}

function emptyForm(): EditForm {
  return {
    title: "", description: "", status: "draft", max_submissions: "",
    send_confirmation: false, confirmation_message: "", allow_edit: false, fields: [],
  };
}

function toEditForm(f: FormAdmin): EditForm {
  return {
    id: f.id,
    title: f.title,
    description: f.description ?? "",
    status: f.status,
    max_submissions: f.max_submissions != null ? String(f.max_submissions) : "",
    send_confirmation: f.send_confirmation,
    confirmation_message: f.confirmation_message ?? "",
    allow_edit: f.allow_edit,
    share_token: f.share_token,
    fields: f.fields.map((fd: FormFieldDef) => ({
      field_type: fd.field_type,
      label: fd.label,
      help_text: fd.help_text ?? "",
      required: fd.required,
      position: fd.position,
      min_value: fd.min_value != null ? String(fd.min_value) : "",
      max_value: fd.max_value != null ? String(fd.max_value) : "",
      min_length: fd.min_length != null ? String(fd.min_length) : "",
      max_length: fd.max_length != null ? String(fd.max_length) : "",
      regex_pattern: fd.regex_pattern ?? "",
      options: fd.options.map((o) => ({ label: o.label, value: o.value ?? "", position: o.position })),
    })),
  };
}

function toPayload(f: EditForm) {
  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  return {
    title: f.title,
    description: f.description || null,
    status: f.status,
    max_submissions: num(f.max_submissions),
    send_confirmation: f.send_confirmation,
    confirmation_message: f.confirmation_message || null,
    allow_edit: f.allow_edit,
    fields: f.fields.map((fd, i) => ({
      field_type: fd.field_type,
      label: fd.label,
      help_text: fd.help_text || null,
      required: fd.required,
      position: i,
      min_value: fd.field_type === "number" ? num(fd.min_value) : null,
      max_value: fd.field_type === "number" ? num(fd.max_value) : null,
      min_length: ["text", "textarea", "email"].includes(fd.field_type) ? num(fd.min_length) : null,
      max_length: ["text", "textarea", "email"].includes(fd.field_type) ? num(fd.max_length) : null,
      regex_pattern: ["text", "textarea", "email"].includes(fd.field_type) ? (fd.regex_pattern || null) : null,
      options: CHOICE_TYPES.includes(fd.field_type)
        ? fd.options.map((o, j) => ({ label: o.label, value: o.value || null, position: j }))
        : [],
    })),
  };
}

export default function AdminFormulieren() {
  const [forms, setForms] = useState<FormSummary[]>([]);
  const [view, setView] = useState<"list" | "edit" | "results">("list");
  const [editing, setEditing] = useState<EditForm | null>(null);
  const [resultsForm, setResultsForm] = useState<FormSummary | null>(null);
  const [resultsData, setResultsData] = useState<ResultsShape | null>(null);
  const [error, setError] = useState("");

  function load() {
    getForms().then((r) => setForms(r.data)).catch((e) => setError(parseApiError(e, "Laden mislukt.")));
  }
  useEffect(() => { load(); }, []);

  async function openEditor(id?: number) {
    setError("");
    if (id) {
      const r = await getForm(id);
      setEditing(toEditForm(r.data));
    } else {
      setEditing(emptyForm());
    }
    setView("edit");
  }

  async function save() {
    if (!editing) return;
    setError("");
    try {
      const payload = toPayload(editing);
      if (editing.id) await updateForm(editing.id, payload);
      else await createForm(payload);
      setView("list");
      setEditing(null);
      load();
    } catch (e) {
      setError(parseApiError(e, "Opslaan mislukt."));
    }
  }

  async function remove(id: number) {
    if (!confirm("Dit formulier en alle inzendingen definitief verwijderen?")) return;
    await deleteForm(id);
    load();
  }

  async function openResults(f: FormSummary) {
    setError("");
    const r = await getFormResults(f.id);
    setResultsForm(f);
    setResultsData(r.data);
    setView("results");
  }

  function copyLink(token: string) {
    const url = `${window.location.origin}/formulier/${token}`;
    navigator.clipboard?.writeText(url);
    alert("Deellink gekopieerd:\n" + url);
  }

  async function download(id: number, format: "csv" | "ods") {
    const resp = await exportForm(id, format);
    const url = URL.createObjectURL(resp.data as Blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `formulier-${id}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  if (view === "edit" && editing) {
    return <FormEditor form={editing} setForm={setEditing} onSave={save} onCancel={() => { setView("list"); setEditing(null); }} error={error} />;
  }

  if (view === "results" && resultsForm && resultsData) {
    return <ResultsView form={resultsForm} data={resultsData} onBack={() => setView("list")} />;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-blue-800">Formulieren</h1>
        <button className="btn-primary btn-sm" onClick={() => openEditor()}>Nieuw formulier</button>
      </div>
      {error && <div className="bg-red-50 text-red-700 rounded-lg p-3 mb-3 text-sm">{error}</div>}
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="py-2 pr-3">Titel</th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2 pr-3">Inzendingen</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {forms.map((f) => (
              <tr key={f.id} className="border-b last:border-0">
                <td className="py-2 pr-3 font-medium">{f.title}</td>
                <td className="py-2 pr-3"><StatusBadge status={f.status} /></td>
                <td className="py-2 pr-3">{f.submission_count}</td>
                <td className="py-2 flex flex-wrap gap-2 justify-end">
                  <button className="text-blue-700 hover:underline" onClick={() => copyLink(f.share_token)}>Deellink</button>
                  <button className="text-blue-700 hover:underline" onClick={() => openEditor(f.id)}>Bewerken</button>
                  <button className="text-blue-700 hover:underline" onClick={() => openResults(f)}>Resultaten</button>
                  <button className="text-blue-700 hover:underline" onClick={() => download(f.id, "csv")}>CSV</button>
                  <button className="text-blue-700 hover:underline" onClick={() => download(f.id, "ods")}>ODS</button>
                  <button className="text-red-600 hover:underline" onClick={() => remove(f.id)}>Verwijderen</button>
                </td>
              </tr>
            ))}
            {forms.length === 0 && <tr><td colSpan={4} className="py-4 text-gray-500">Nog geen formulieren.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    draft: "bg-gray-100 text-gray-600",
    open: "bg-green-100 text-green-700",
    closed: "bg-amber-100 text-amber-700",
  };
  const label: Record<string, string> = { draft: "Concept", open: "Open", closed: "Gesloten" };
  return <span className={`text-xs px-2 py-1 rounded-full ${map[status] ?? ""}`}>{label[status] ?? status}</span>;
}

// ── Editor ───────────────────────────────────────────────────────────────────

function FormEditor({
  form, setForm, onSave, onCancel, error,
}: {
  form: EditForm;
  setForm: (f: EditForm) => void;
  onSave: () => void;
  onCancel: () => void;
  error: string;
}) {
  function patch(p: Partial<EditForm>) { setForm({ ...form, ...p }); }
  function patchField(i: number, p: Partial<EditField>) {
    const fields = form.fields.map((f, idx) => (idx === i ? { ...f, ...p } : f));
    setForm({ ...form, fields });
  }
  function addField() { setForm({ ...form, fields: [...form.fields, emptyField()] }); }
  function removeField(i: number) { setForm({ ...form, fields: form.fields.filter((_, idx) => idx !== i) }); }
  function moveField(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= form.fields.length) return;
    const fields = [...form.fields];
    [fields[i], fields[j]] = [fields[j], fields[i]];
    setForm({ ...form, fields });
  }
  function addOption(fi: number) {
    const f = form.fields[fi];
    patchField(fi, { options: [...f.options, { label: "", value: "", position: f.options.length }] });
  }
  function patchOption(fi: number, oi: number, label: string) {
    const f = form.fields[fi];
    patchField(fi, { options: f.options.map((o, idx) => (idx === oi ? { ...o, label } : o)) });
  }
  function removeOption(fi: number, oi: number) {
    const f = form.fields[fi];
    patchField(fi, { options: f.options.filter((_, idx) => idx !== oi) });
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-blue-800">{form.id ? "Formulier bewerken" : "Nieuw formulier"}</h1>
        <div className="flex gap-2">
          <button className="btn-secondary btn-sm" onClick={onCancel}>Annuleren</button>
          <button className="btn-primary btn-sm" onClick={onSave}>Opslaan</button>
        </div>
      </div>
      {error && <div className="bg-red-50 text-red-700 rounded-lg p-3 mb-3 text-sm">{error}</div>}

      <div className="card mb-4 space-y-3">
        <div>
          <label className="block font-medium mb-1">Titel</label>
          <input className="input w-full" value={form.title} onChange={(e) => patch({ title: e.target.value })} />
        </div>
        <div>
          <label className="block font-medium mb-1">Beschrijving (bv. wat je nodig hebt, aantallen)</label>
          <textarea className="input w-full" rows={4} value={form.description} onChange={(e) => patch({ description: e.target.value })} />
        </div>
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block font-medium mb-1">Status</label>
            <select className="input" value={form.status} onChange={(e) => patch({ status: e.target.value })}>
              <option value="draft">Concept</option>
              <option value="open">Open</option>
              <option value="closed">Gesloten</option>
            </select>
          </div>
          <div>
            <label className="block font-medium mb-1">Max. inzendingen</label>
            <input className="input w-32" type="number" value={form.max_submissions} onChange={(e) => patch({ max_submissions: e.target.value })} placeholder="onbeperkt" />
          </div>
        </div>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={form.send_confirmation} onChange={(e) => patch({ send_confirmation: e.target.checked })} />
          Bevestigingsmail sturen (als de invuller een e-mailadres opgeeft)
        </label>
        {form.send_confirmation && (
          <div>
            <label className="block font-medium mb-1">Tekst bevestigingsmail (optioneel)</label>
            <textarea className="input w-full" rows={2} value={form.confirmation_message} onChange={(e) => patch({ confirmation_message: e.target.value })} />
          </div>
        )}
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={form.allow_edit} onChange={(e) => patch({ allow_edit: e.target.checked })} />
          Invuller mag antwoord nadien wijzigen via een link
        </label>
      </div>

      <div className="space-y-3">
        {form.fields.map((f, i) => (
          <div key={i} className="card">
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-sm font-medium mb-1">Type</label>
                <select className="input" value={f.field_type} onChange={(e) => patchField(i, { field_type: e.target.value })}>
                  {FIELD_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div className="flex-1 min-w-[200px]">
                <label className="block text-sm font-medium mb-1">Vraag / label</label>
                <input className="input w-full" value={f.label} onChange={(e) => patchField(i, { label: e.target.value })} />
              </div>
              <label className="flex items-center gap-2 pb-2">
                <input type="checkbox" checked={f.required} onChange={(e) => patchField(i, { required: e.target.checked })} />
                Verplicht
              </label>
              <div className="flex gap-1 pb-1">
                <button className="btn-secondary btn-sm" onClick={() => moveField(i, -1)}>↑</button>
                <button className="btn-secondary btn-sm" onClick={() => moveField(i, 1)}>↓</button>
                <button className="btn-danger btn-sm" onClick={() => removeField(i)}>✕</button>
              </div>
            </div>

            <input className="input w-full mt-2" placeholder="Hulptekst (optioneel)" value={f.help_text} onChange={(e) => patchField(i, { help_text: e.target.value })} />

            {CHOICE_TYPES.includes(f.field_type) && (
              <div className="mt-3 pl-3 border-l-2 border-gray-200 space-y-2">
                <p className="text-sm font-medium text-gray-600">Opties</p>
                {f.options.map((o, oi) => (
                  <div key={oi} className="flex gap-2">
                    <input className="input flex-1" value={o.label} onChange={(e) => patchOption(i, oi, e.target.value)} placeholder={`Optie ${oi + 1}`} />
                    <button className="btn-danger btn-sm" onClick={() => removeOption(i, oi)}>✕</button>
                  </div>
                ))}
                <button className="btn-secondary btn-sm" onClick={() => addOption(i)}>+ Optie</button>
              </div>
            )}

            {f.field_type === "number" && (
              <div className="mt-3 flex gap-3">
                <input className="input w-32" placeholder="min" value={f.min_value} onChange={(e) => patchField(i, { min_value: e.target.value })} />
                <input className="input w-32" placeholder="max" value={f.max_value} onChange={(e) => patchField(i, { max_value: e.target.value })} />
              </div>
            )}

            {["text", "textarea", "email"].includes(f.field_type) && (
              <div className="mt-3 flex flex-wrap gap-3">
                <input className="input w-36" placeholder="min. lengte" value={f.min_length} onChange={(e) => patchField(i, { min_length: e.target.value })} />
                <input className="input w-36" placeholder="max. lengte" value={f.max_length} onChange={(e) => patchField(i, { max_length: e.target.value })} />
              </div>
            )}
          </div>
        ))}
        <button className="btn-secondary" onClick={addField}>+ Veld toevoegen</button>
      </div>
    </div>
  );
}

// ── Resultaten ────────────────────────────────────────────────────────────────

type ResultsField = {
  field_id: number;
  label: string;
  field_type: string;
  response_count?: number;
  options?: { option_id: number; label: string; count: number }[];
  distribution?: { rating: number; label: string; count: number }[];
  average?: number | null;
  min?: number | null;
  max?: number | null;
  answers?: string[];
};
type ResultsShape = {
  submission_count: number;
  last_submission: string | null;
  fields: ResultsField[];
};

function Bar({ count, max }: { count: number; max: number }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-100 rounded h-4 overflow-hidden">
        <div className="bg-blue-600 h-4" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm text-gray-600 w-10 text-right">{count}</span>
    </div>
  );
}

function ResultsView({ form, data, onBack }: { form: FormSummary; data: ResultsShape; onBack: () => void }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-blue-800">Resultaten — {form.title}</h1>
        <button className="btn-secondary btn-sm" onClick={onBack}>Terug</button>
      </div>
      <p className="text-gray-600 mb-4">
        {data.submission_count} inzending{data.submission_count === 1 ? "" : "en"}
        {data.last_submission && <> · laatste {new Date(data.last_submission).toLocaleString("nl-BE")}</>}
      </p>

      <div className="space-y-4">
        {data.fields.map((f) => (
          <div key={f.field_id} className="card">
            <h3 className="font-semibold mb-2">{f.label}</h3>

            {f.options && (
              <div className="space-y-1">
                {f.options.map((o) => (
                  <div key={o.option_id}>
                    <div className="text-sm text-gray-700">{o.label}</div>
                    <Bar count={o.count} max={Math.max(1, ...f.options!.map((x) => x.count))} />
                  </div>
                ))}
              </div>
            )}

            {f.distribution && (
              <div className="space-y-1">
                {typeof f.average === "number" && <p className="text-sm text-gray-600 mb-1">Gemiddelde: <strong>{f.average}</strong> / 5</p>}
                {f.distribution.map((d) => (
                  <div key={d.rating}>
                    <div className="text-sm text-gray-700">{d.label}</div>
                    <Bar count={d.count} max={Math.max(1, ...f.distribution!.map((x) => x.count))} />
                  </div>
                ))}
              </div>
            )}

            {f.field_type === "number" && (
              <p className="text-sm text-gray-700">
                {f.response_count ?? 0} antwoorden · gem. {f.average ?? "—"} · min {f.min ?? "—"} · max {f.max ?? "—"}
              </p>
            )}

            {f.answers && (
              <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1 max-h-60 overflow-y-auto">
                {f.answers.map((a, idx) => <li key={idx}>{a}</li>)}
                {f.answers.length === 0 && <li className="list-none text-gray-400">Geen antwoorden.</li>}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
