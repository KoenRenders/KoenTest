"use client";
import { useEffect, useState } from "react";
import {
  getForms, getForm, createForm, updateForm, deleteForm, getFormResults, exportForm,
  getFormSubmissions, deleteFormSubmission,
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
  { value: "phone", label: "Telefoon / gsm" },
  { value: "info", label: "Tekstblok (info)" },
];
const CHOICE_TYPES = ["select", "radio", "checkbox"];

type EditOption = { id?: number; label: string; value: string; position: number; is_other: boolean; skip_to_section_index: number | null; skip_to_end: boolean };
type EditSection = { id?: number; title: string; description: string; next_section_index: number | null; next_is_end: boolean };
type EditField = {
  id?: number;
  field_type: string;
  label: string;
  help_text: string;
  required: boolean;
  position: number;
  section_index: number | null;
  min_value: string;
  max_value: string;
  min_length: string;
  max_length: string;
  regex_pattern: string;
  rating_max: string;
  rating_low_label: string;
  rating_high_label: string;
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
  is_anonymous: boolean;
  share_token?: string;
  sections: EditSection[];
  fields: EditField[];
};

function emptyField(): EditField {
  return {
    field_type: "text", label: "", help_text: "", required: false, position: 0,
    section_index: null,
    min_value: "", max_value: "", min_length: "", max_length: "", regex_pattern: "",
    rating_max: "", rating_low_label: "", rating_high_label: "", options: [],
  };
}

function emptyForm(): EditForm {
  return {
    title: "", description: "", status: "draft", max_submissions: "",
    send_confirmation: false, confirmation_message: "", allow_edit: false, is_anonymous: false, sections: [], fields: [],
  };
}

function toEditForm(f: FormAdmin): EditForm {
  const sorted = [...(f.sections ?? [])].sort((a, b) => a.position - b.position);
  const sectionIndex: Record<number, number> = {};
  sorted.forEach((s, i) => { sectionIndex[s.id] = i; });
  return {
    id: f.id,
    title: f.title,
    description: f.description ?? "",
    status: f.status,
    max_submissions: f.max_submissions != null ? String(f.max_submissions) : "",
    send_confirmation: f.send_confirmation,
    confirmation_message: f.confirmation_message ?? "",
    allow_edit: f.allow_edit,
    is_anonymous: !!f.is_anonymous,
    share_token: f.share_token,
    sections: sorted.map((s) => ({
      id: s.id,
      title: s.title ?? "",
      description: s.description ?? "",
      next_section_index: s.next_section_id != null && s.next_section_id in sectionIndex ? sectionIndex[s.next_section_id] : null,
      next_is_end: !!s.next_is_end,
    })),
    fields: f.fields.map((fd: FormFieldDef) => ({
      id: fd.id,
      field_type: fd.field_type,
      label: fd.label,
      help_text: fd.help_text ?? "",
      required: fd.required,
      position: fd.position,
      section_index: fd.section_id != null && fd.section_id in sectionIndex ? sectionIndex[fd.section_id] : null,
      min_value: fd.min_value != null ? String(fd.min_value) : "",
      max_value: fd.max_value != null ? String(fd.max_value) : "",
      min_length: fd.min_length != null ? String(fd.min_length) : "",
      max_length: fd.max_length != null ? String(fd.max_length) : "",
      regex_pattern: fd.regex_pattern ?? "",
      rating_max: fd.rating_max != null ? String(fd.rating_max) : "",
      rating_low_label: fd.rating_low_label ?? "",
      rating_high_label: fd.rating_high_label ?? "",
      options: fd.options.map((o) => ({
        id: o.id, label: o.label, value: o.value ?? "", position: o.position, is_other: !!o.is_other,
        skip_to_section_index: o.skip_to_section_id != null && o.skip_to_section_id in sectionIndex ? sectionIndex[o.skip_to_section_id] : null,
        skip_to_end: !!o.skip_to_end,
      })),
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
    is_anonymous: f.is_anonymous,
    sections: f.sections.map((s, i) => ({
      id: s.id ?? null,
      title: s.title || null,
      description: s.description || null,
      position: i,
      next_section_index: s.next_section_index != null && s.next_section_index < f.sections.length ? s.next_section_index : null,
      next_is_end: s.next_is_end,
    })),
    fields: f.fields.map((fd, i) => ({
      id: fd.id ?? null,
      field_type: fd.field_type,
      label: fd.label,
      help_text: fd.help_text || null,
      required: fd.required,
      position: i,
      section_index: fd.section_index != null && fd.section_index < f.sections.length ? fd.section_index : null,
      min_value: fd.field_type === "number" ? num(fd.min_value) : null,
      max_value: fd.field_type === "number" ? num(fd.max_value) : null,
      min_length: ["text", "textarea", "email"].includes(fd.field_type) ? num(fd.min_length) : null,
      max_length: ["text", "textarea", "email"].includes(fd.field_type) ? num(fd.max_length) : null,
      regex_pattern: ["text", "textarea", "email"].includes(fd.field_type) ? (fd.regex_pattern || null) : null,
      rating_max: fd.field_type === "rating" ? num(fd.rating_max) : null,
      rating_low_label: fd.field_type === "rating" ? (fd.rating_low_label || null) : null,
      rating_high_label: fd.field_type === "rating" ? (fd.rating_high_label || null) : null,
      options: CHOICE_TYPES.includes(fd.field_type)
        ? fd.options.map((o, j) => ({
            id: o.id ?? null, label: o.label, value: o.value || null, position: j, is_other: o.is_other,
            // Branching enkel voor radio/select (#336).
            skip_to_section_index: ["radio", "select"].includes(fd.field_type) && o.skip_to_section_index != null && o.skip_to_section_index < f.sections.length ? o.skip_to_section_index : null,
            skip_to_end: ["radio", "select"].includes(fd.field_type) ? o.skip_to_end : false,
          }))
        : [],
    })),
  };
}

export default function AdminFormulieren() {
  const [forms, setForms] = useState<FormSummary[]>([]);
  const [view, setView] = useState<"list" | "edit" | "results" | "submissions">("list");
  const [editing, setEditing] = useState<EditForm | null>(null);
  const [resultsForm, setResultsForm] = useState<FormSummary | null>(null);
  const [resultsData, setResultsData] = useState<ResultsShape | null>(null);
  const [subsForm, setSubsForm] = useState<FormSummary | null>(null);
  const [subsData, setSubsData] = useState<SubmissionsShape | null>(null);
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
    // Vraag/label verplicht (#340).
    if (editing.fields.some((f) => !f.label.trim())) {
      setError("Elk veld heeft een vraag/label nodig.");
      return;
    }
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

  async function openSubmissions(f: FormSummary) {
    setError("");
    const r = await getFormSubmissions(f.id);
    setSubsForm(f);
    setSubsData(r.data);
    setView("submissions");
  }

  async function removeSubmission(submissionId: number) {
    if (!subsForm) return;
    if (!confirm("Deze inzending definitief verwijderen?")) return;
    await deleteFormSubmission(subsForm.id, submissionId);
    const r = await getFormSubmissions(subsForm.id);
    setSubsData(r.data);
    load();
  }

  async function copyToClipboard(text: string): Promise<boolean> {
    // navigator.clipboard werkt enkel in een secure context (HTTPS/localhost);
    // op HDEV (HTTP) valt dit terug op een tijdelijk textarea + execCommand (#338).
    try {
      if (window.isSecureContext && navigator.clipboard) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      /* val terug op de legacy-methode */
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }

  async function copyLink(f: FormSummary) {
    const url = `${window.location.origin}/formulier/${f.share_token}`;
    const ok = await copyToClipboard(url);
    const draftWarn = f.status === "draft"
      ? "\n\nLet op: dit formulier staat op Concept — de link werkt pas publiek zodra de status op Open staat."
      : "";
    if (ok) {
      alert("Deellink gekopieerd:\n" + url + draftWarn);
    } else {
      // Kopiëren lukte niet — toon de link zodat de gebruiker hem zelf kan kopiëren.
      window.prompt("Kopieer de deellink (Ctrl+C):", url);
    }
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

  function downloadBlob(content: string, filename: string, type: string) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  // Exporteert de formulier-definitie als JSON (zonder id's) — een sjabloon dat je
  // opnieuw kan importeren of aan een AI kan geven (#367).
  async function exportJson(id: number) {
    setError("");
    try {
      const r = await getForm(id);
      const payload = toPayload(toEditForm(r.data));
      const clean = JSON.stringify(payload, (k, v) => (k === "id" ? undefined : v), 2);
      downloadBlob(clean, `formulier-${id}.json`, "application/json");
    } catch (e) {
      setError(parseApiError(e, "Exporteren mislukt."));
    }
  }

  // Importeert een formulier uit een JSON-bestand → aangemaakt als concept (#367).
  async function importJsonFile(file: File | null | undefined, input: HTMLInputElement) {
    input.value = ""; // reset zodat hetzelfde bestand opnieuw gekozen kan worden
    if (!file) return;
    setError("");
    let payload: unknown;
    try {
      payload = JSON.parse(await file.text());
    } catch {
      setError("Ongeldig JSON-bestand: kon de inhoud niet lezen.");
      return;
    }
    if (!payload || typeof payload !== "object" || !(payload as { title?: unknown }).title) {
      setError("Ongeldig formulier-JSON: veld 'title' ontbreekt.");
      return;
    }
    try {
      await createForm(payload);
      load();
      alert("Formulier geïmporteerd als concept. Controleer het en zet de status op 'Open' wanneer klaar.");
    } catch (e) {
      setError(parseApiError(e, "Importeren mislukt — is dit een geldig formulier-JSON?"));
    }
  }

  if (view === "edit" && editing) {
    return <FormEditor form={editing} setForm={setEditing} onSave={save} onCancel={() => { setView("list"); setEditing(null); }} error={error} />;
  }

  if (view === "results" && resultsForm && resultsData) {
    return <ResultsView form={resultsForm} data={resultsData} onBack={() => setView("list")} />;
  }

  if (view === "submissions" && subsForm && subsData) {
    return <SubmissionsView form={subsForm} data={subsData} onBack={() => setView("list")} onDelete={removeSubmission} />;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-blue-800">Formulieren</h1>
        <div className="flex flex-wrap items-center gap-2">
          <a className="text-blue-700 hover:underline text-sm" href="/form-json-formaat.md" target="_blank" rel="noopener noreferrer">Formaat (voor AI)</a>
          <label className="btn-secondary btn-sm cursor-pointer">
            Importeer JSON
            <input type="file" accept="application/json,.json" className="hidden" onChange={(e) => importJsonFile(e.target.files?.[0], e.currentTarget)} />
          </label>
          <button className="btn-primary btn-sm" onClick={() => openEditor()}>Nieuw formulier</button>
        </div>
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
                  <button className="text-blue-700 hover:underline" onClick={() => copyLink(f)}>Deellink</button>
                  <button className="text-blue-700 hover:underline" onClick={() => openEditor(f.id)}>Bewerken</button>
                  <button className="text-blue-700 hover:underline" onClick={() => openResults(f)}>Resultaten</button>
                  <button className="text-blue-700 hover:underline" onClick={() => openSubmissions(f)}>Inzendingen</button>
                  <button className="text-blue-700 hover:underline" onClick={() => window.open(`/admin/formulieren/${f.id}/afdruk`, "_blank")}>Afdrukken</button>
                  <button className="text-blue-700 hover:underline" onClick={() => download(f.id, "csv")}>CSV</button>
                  <button className="text-blue-700 hover:underline" onClick={() => download(f.id, "ods")}>ODS</button>
                  <button className="text-blue-700 hover:underline" onClick={() => exportJson(f.id)}>JSON</button>
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
  function addField(sectionIndex: number | null = null) {
    setForm({ ...form, fields: [...form.fields, { ...emptyField(), section_index: sectionIndex }] });
  }
  function removeField(i: number) { setForm({ ...form, fields: form.fields.filter((_, idx) => idx !== i) }); }
  function moveField(i: number, dir: -1 | 1) {
    // Verplaats binnen dezelfde sectie: zoek de dichtstbijzijnde buur met hetzelfde section_index.
    const sec = form.fields[i].section_index;
    let j = i + dir;
    while (j >= 0 && j < form.fields.length && form.fields[j].section_index !== sec) j += dir;
    if (j < 0 || j >= form.fields.length) return;
    const fields = [...form.fields];
    [fields[i], fields[j]] = [fields[j], fields[i]];
    setForm({ ...form, fields });
  }
  function addOption(fi: number) {
    const f = form.fields[fi];
    patchField(fi, { options: [...f.options, { label: "", value: "", position: f.options.length, is_other: false, skip_to_section_index: null, skip_to_end: false }] });
  }
  function patchOption(fi: number, oi: number, p: Partial<EditOption>) {
    const f = form.fields[fi];
    patchField(fi, { options: f.options.map((o, idx) => (idx === oi ? { ...o, ...p } : o)) });
  }
  function removeOption(fi: number, oi: number) {
    const f = form.fields[fi];
    patchField(fi, { options: f.options.filter((_, idx) => idx !== oi) });
  }
  // Secties (#335)
  function addSection() { setForm({ ...form, sections: [...form.sections, { title: "", description: "", next_section_index: null, next_is_end: false }] }); }
  function patchSection(i: number, p: Partial<EditSection>) {
    setForm({ ...form, sections: form.sections.map((s, idx) => (idx === i ? { ...s, ...p } : s)) });
  }
  function removeSection(i: number) {
    // Verschuif/ontkoppel elke index die naar deze sectie (of een latere) verwees.
    const shift = (idx: number | null): number | null =>
      idx == null ? null : idx === i ? null : idx > i ? idx - 1 : idx;
    const fields = form.fields.map((f) => ({
      ...f,
      section_index: shift(f.section_index),
      options: f.options.map((o) => ({ ...o, skip_to_section_index: shift(o.skip_to_section_index) })),
    }));
    const sections = form.sections
      .filter((_, idx) => idx !== i)
      .map((s) => ({ ...s, next_section_index: shift(s.next_section_index) }));
    setForm({ ...form, sections, fields });
  }
  function moveSection(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= form.sections.length) return;
    // Verwissel sectie i en j en herindexeer élke verwijzing (veld-sectie, sectie-
    // navigatie, keuze-sprong) zodat ze naar dezelfde logische sectie blijven wijzen.
    const map = (idx: number | null): number | null =>
      idx == null ? null : idx === i ? j : idx === j ? i : idx;
    const sections = [...form.sections];
    [sections[i], sections[j]] = [sections[j], sections[i]];
    const remapped = sections.map((s) => ({ ...s, next_section_index: map(s.next_section_index) }));
    const fields = form.fields.map((f) => ({
      ...f,
      section_index: map(f.section_index),
      options: f.options.map((o) => ({ ...o, skip_to_section_index: map(o.skip_to_section_index) })),
    }));
    setForm({ ...form, sections: remapped, fields });
  }

  // Eén veldkaart renderen op globale index i (los van in welke sectie-groep het staat).
  function renderFieldCard(i: number) {
    const f = form.fields[i];
    return (
      <div key={i} className="card">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-sm font-medium mb-1">Type</label>
            <select className="input" value={f.field_type} onChange={(e) => patchField(i, { field_type: e.target.value })}>
              {FIELD_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium mb-1">Vraag / label <span className="text-red-600">*</span></label>
            <input className={`input w-full ${f.label.trim() ? "" : "border-red-400"}`} value={f.label} onChange={(e) => patchField(i, { label: e.target.value })} placeholder="verplicht" />
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
              <div key={oi} className="flex flex-wrap gap-2 items-center">
                <input className="input flex-1 min-w-[160px]" value={o.label} onChange={(e) => patchOption(i, oi, { label: e.target.value })} placeholder={`Optie ${oi + 1}`} />
                <label className="flex items-center gap-1 text-xs text-gray-600 whitespace-nowrap">
                  <input type="checkbox" checked={o.is_other} onChange={(e) => patchOption(i, oi, { is_other: e.target.checked })} />
                  "Andere…" (vrij tekstveld)
                </label>
                {["radio", "select"].includes(f.field_type) && form.sections.length > 0 && (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-gray-500 whitespace-nowrap">ga naar →</span>
                    <select
                      className="input"
                      value={o.skip_to_end ? "end" : o.skip_to_section_index != null ? String(o.skip_to_section_index) : ""}
                      onChange={(e) => {
                        const v = e.target.value;
                        if (v === "") patchOption(i, oi, { skip_to_section_index: null, skip_to_end: false });
                        else if (v === "end") patchOption(i, oi, { skip_to_section_index: null, skip_to_end: true });
                        else patchOption(i, oi, { skip_to_section_index: Number(v), skip_to_end: false });
                      }}
                    >
                      <option value="">— (gewone volgorde)</option>
                      {form.sections.map((s2, si) => (si > (f.section_index ?? -1) ? <option key={si} value={si}>{s2.title || `Sectie ${si + 1}`}</option> : null))}
                      <option value="end">einde</option>
                    </select>
                  </div>
                )}
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

        {f.field_type === "rating" && (
          <div className="mt-3 flex flex-wrap gap-3 items-end">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Aantal punten</label>
              <input
                className="input w-28"
                type="number"
                min={1}
                max={10}
                placeholder="5"
                value={f.rating_max}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === "") { patchField(i, { rating_max: "" }); return; }
                  const capped = Math.max(1, Math.min(10, Math.round(Number(raw))));
                  patchField(i, { rating_max: String(capped) });
                }}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Label links (laag)</label>
              <input className="input w-44" placeholder="bv. Onbelangrijk" value={f.rating_low_label} onChange={(e) => patchField(i, { rating_low_label: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Label rechts (hoog)</label>
              <input className="input w-44" placeholder="bv. Zeer belangrijk" value={f.rating_high_label} onChange={(e) => patchField(i, { rating_high_label: e.target.value })} />
            </div>
            <p className="text-xs text-gray-400 w-full">Leeg laten = standaard 5 punten ("zeer slecht → zeer goed"). Maximum 10.</p>
          </div>
        )}

        {["text", "textarea", "email"].includes(f.field_type) && (
          <div className="mt-3 flex flex-wrap gap-3">
            <input className="input w-36" placeholder="min. lengte" value={f.min_length} onChange={(e) => patchField(i, { min_length: e.target.value })} />
            <input className="input w-36" placeholder="max. lengte" value={f.max_length} onChange={(e) => patchField(i, { max_length: e.target.value })} />
          </div>
        )}
      </div>
    );
  }

  const globalIdx = form.fields.map((_, i) => i);
  const ungroupedIdx = globalIdx.filter((i) => form.fields[i].section_index == null);
  const idxOfSection = (si: number) => globalIdx.filter((i) => form.fields[i].section_index === si);

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
          <input type="checkbox" checked={form.is_anonymous} onChange={(e) => patch({ is_anonymous: e.target.checked })} />
          Anoniem — geen naam/e-mail vragen, geen bevestigingsmail, geen invuller bewaard
        </label>
        {!form.is_anonymous && (
          <>
            <p className="text-sm text-gray-500">Bij een niet-anoniem formulier vragen we onderaan naam + e-mail van de invuller (los van de vragen in het formulier).</p>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={form.send_confirmation} onChange={(e) => patch({ send_confirmation: e.target.checked })} />
              Bevestigingsmail sturen (naar het opgegeven contact-e-mailadres)
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={form.allow_edit} onChange={(e) => patch({ allow_edit: e.target.checked })} />
              Invuller mag antwoord nadien wijzigen via een link
            </label>
          </>
        )}
        <div>
          <label className="block font-medium mb-1">Bedanktekst na indienen (optioneel)</label>
          <textarea className="input w-full" rows={2} value={form.confirmation_message} onChange={(e) => patch({ confirmation_message: e.target.value })}
            placeholder="Bv. Hartelijk bedankt voor het invullen!" />
          <p className="text-xs text-gray-400 mt-1">Verschijnt op het bedankt-scherm na indienen (en in de bevestigingsmail als die aanstaat).</p>
        </div>
      </div>

      {/* Ongegroepeerde vragen (bovenaan, zoals in Google Forms vóór de eerste sectie). */}
      {ungroupedIdx.length > 0 && (
        <div className="space-y-3 mb-4">{ungroupedIdx.map(renderFieldCard)}</div>
      )}

      {/* Secties met hun vragen eronder (Google-stijl). */}
      {form.sections.map((s, si) => (
        <div key={si} className="mb-6">
          <div className="bg-blue-700 text-white rounded-t-xl px-4 py-2 flex items-center justify-between">
            <span className="font-semibold">Sectie {si + 1} van {form.sections.length}</span>
            <div className="flex gap-1">
              <button className="px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-500" onClick={() => moveSection(si, -1)} title="Sectie omhoog">↑</button>
              <button className="px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-500" onClick={() => moveSection(si, 1)} title="Sectie omlaag">↓</button>
              <button className="px-2 py-0.5 rounded bg-red-600 hover:bg-red-500" onClick={() => removeSection(si)} title="Sectie verwijderen">✕</button>
            </div>
          </div>
          <div className="card rounded-t-none border-t-0 space-y-2">
            <input className="input w-full font-medium" value={s.title} onChange={(e) => patchSection(si, { title: e.target.value })} placeholder={`Sectietitel ${si + 1}`} />
            <input className="input w-full" value={s.description} onChange={(e) => patchSection(si, { description: e.target.value })} placeholder="Beschrijving / uitleg (optioneel)" />
            <div className="flex items-center gap-1 text-sm">
              <span className="text-gray-500 whitespace-nowrap">na deze sectie →</span>
              <select
                className="input"
                value={s.next_is_end ? "end" : s.next_section_index != null ? String(s.next_section_index) : ""}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "") patchSection(si, { next_section_index: null, next_is_end: false });
                  else if (v === "end") patchSection(si, { next_section_index: null, next_is_end: true });
                  else patchSection(si, { next_section_index: Number(v), next_is_end: false });
                }}
              >
                <option value="">volgende sectie</option>
                {form.sections.map((s2, k) => (k > si ? <option key={k} value={k}>→ {s2.title || `Sectie ${k + 1}`}</option> : null))}
                <option value="end">→ einde</option>
              </select>
            </div>
          </div>
          <div className="space-y-3 mt-3 pl-3 border-l-4 border-blue-100">
            {idxOfSection(si).map(renderFieldCard)}
            <button className="btn-secondary btn-sm" onClick={() => addField(si)}>+ Vraag in deze sectie</button>
          </div>
        </div>
      ))}

      <div className="flex flex-wrap gap-2">
        <button className="btn-secondary" onClick={() => addField(null)}>+ Vraag {form.sections.length > 0 ? "(zonder sectie)" : ""}</button>
        <button className="btn-secondary" onClick={addSection}>+ Sectie toevoegen</button>
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

type SubmissionRow = {
  id: number;
  submitted_at: string | null;
  submitter_name: string | null;
  submitter_email: string | null;
  values: string[];
};
type SubmissionsShape = {
  fields: string[];
  submissions: SubmissionRow[];
};

function SubmissionsView({ form, data, onBack, onDelete }: {
  form: FormSummary;
  data: SubmissionsShape;
  onBack: () => void;
  onDelete: (submissionId: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-blue-800">Inzendingen — {form.title}</h1>
        <button className="btn-secondary btn-sm" onClick={onBack}>Terug</button>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="py-2 pr-3 whitespace-nowrap">Ingediend op</th>
              <th className="py-2 pr-3">Naam</th>
              <th className="py-2 pr-3">E-mail</th>
              {data.fields.map((label, i) => <th key={i} className="py-2 pr-3">{label}</th>)}
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {data.submissions.map((s) => (
              <tr key={s.id} className="border-b last:border-0 align-top">
                <td className="py-2 pr-3 whitespace-nowrap text-gray-600">
                  {s.submitted_at ? new Date(s.submitted_at).toLocaleString("nl-BE") : "—"}
                </td>
                <td className="py-2 pr-3">{s.submitter_name || "—"}</td>
                <td className="py-2 pr-3">{s.submitter_email || "—"}</td>
                {s.values.map((v, i) => <td key={i} className="py-2 pr-3 whitespace-pre-wrap">{v || "—"}</td>)}
                <td className="py-2 text-right">
                  <button className="text-red-600 hover:underline" onClick={() => onDelete(s.id)}>Verwijderen</button>
                </td>
              </tr>
            ))}
            {data.submissions.length === 0 && (
              <tr><td colSpan={data.fields.length + 4} className="py-4 text-gray-500">Nog geen inzendingen.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

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
