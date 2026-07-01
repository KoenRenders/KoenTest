"use client";
import { useState } from "react";
import type { PublicFormField, FormSection, AnswerPayload } from "@/lib/types";

const RATING_LABELS: Record<number, string> = {
  1: "Zeer slecht",
  2: "Slecht",
  3: "Neutraal",
  4: "Goed",
  5: "Zeer goed",
};

type AnswerState = {
  text?: string;
  number?: string;
  optionIds?: number[];
  rating?: number;
  otherText?: string;
};

export interface DynamicFormInitial {
  submitter_name?: string | null;
  submitter_email?: string | null;
  answers: AnswerPayload[];
}

function buildInitial(fields: PublicFormField[], initial?: DynamicFormInitial): Record<number, AnswerState> {
  const state: Record<number, AnswerState> = {};
  for (const f of fields) state[f.id] = { optionIds: [] };
  if (initial) {
    for (const a of initial.answers) {
      state[a.field_id] = {
        text: a.text ?? undefined,
        number: a.number != null ? String(a.number) : undefined,
        optionIds: a.option_ids ?? [],
        rating: a.rating ?? undefined,
        otherText: a.other_text ?? undefined,
      };
    }
  }
  return state;
}

export default function DynamicForm({
  fields,
  sections,
  initial,
  submitting,
  submitLabel = "Versturen",
  collectContact = false,
  requireEmail = false,
  onSubmit,
}: {
  fields: PublicFormField[];
  sections?: FormSection[];
  initial?: DynamicFormInitial;
  submitting?: boolean;
  submitLabel?: string;
  collectContact?: boolean;
  requireEmail?: boolean;
  onSubmit: (payload: { answers: AnswerPayload[]; submitter_name?: string; submitter_email?: string }) => void;
}) {
  const [answers, setAnswers] = useState<Record<number, AnswerState>>(() => buildInitial(fields, initial));
  const [contactName, setContactName] = useState(initial?.submitter_name ?? "");
  const [contactEmail, setContactEmail] = useState(initial?.submitter_email ?? "");

  function set(fieldId: number, patch: Partial<AnswerState>) {
    setAnswers((prev) => ({ ...prev, [fieldId]: { ...prev[fieldId], ...patch } }));
  }

  function toggleOption(fieldId: number, optionId: number, multi: boolean) {
    setAnswers((prev) => {
      const current = prev[fieldId]?.optionIds ?? [];
      let next: number[];
      if (multi) {
        next = current.includes(optionId) ? current.filter((x) => x !== optionId) : [...current, optionId];
      } else {
        next = [optionId];
      }
      return { ...prev, [fieldId]: { ...prev[fieldId], optionIds: next } };
    });
  }

  // ── Secties + branching (#336) ──────────────────────────────────────────────
  const orderedSections = [...(sections ?? [])].sort((s1, s2) => s1.position - s2.position);
  const ungrouped = fields.filter((f) => f.section_id == null);
  const hasBranching =
    fields.some((f) => f.options?.some((o) => o.skip_to_section_id != null || o.skip_to_end)) ||
    orderedSections.some((s) => s.next_section_id != null || s.next_is_end);

  const [path, setPath] = useState<number[]>(() => (orderedSections.length ? [orderedSections[0].id] : []));
  const [wizardError, setWizardError] = useState("");

  function fieldsOf(sectionId: number) {
    return fields.filter((f) => f.section_id === sectionId);
  }
  function missingRequired(fs: PublicFormField[]): boolean {
    return fs.some((f) => {
      if (f.field_type === "info" || !f.required) return false;
      const a = answers[f.id] || {};
      const has = (!!a.text && a.text.trim() !== "") || !!a.number || (a.optionIds?.length ?? 0) > 0 || a.rating != null;
      return !has;
    });
  }
  function nextFrom(sectionId: number): number | "end" | null {
    for (const f of fieldsOf(sectionId)) {
      if (f.field_type === "radio" || f.field_type === "select") {
        const chosen = (answers[f.id]?.optionIds ?? [])[0];
        const opt = f.options.find((o) => o.id === chosen);
        if (opt) {
          if (opt.skip_to_end) return "end";
          if (opt.skip_to_section_id != null) return opt.skip_to_section_id;
        }
      }
    }
    const sec = orderedSections.find((s) => s.id === sectionId);
    if (sec?.next_is_end) return "end";
    if (sec?.next_section_id != null) return sec.next_section_id;
    const idx = orderedSections.findIndex((s) => s.id === sectionId);
    if (idx >= 0 && idx + 1 < orderedSections.length) return orderedSections[idx + 1].id;
    return null;
  }
  const currentId: number | undefined = path[path.length - 1];
  const currentFields = currentId != null ? fieldsOf(currentId) : [];
  const stepFields = path.length === 1 ? [...ungrouped, ...currentFields] : currentFields;
  const isLastStep = currentId == null || nextFrom(currentId) === "end" || nextFrom(currentId) === null;

  function goNext() {
    if (missingRequired(stepFields)) { setWizardError("Vul de verplichte velden in voor je verdergaat."); return; }
    setWizardError("");
    const nxt = currentId != null ? nextFrom(currentId) : null;
    if (nxt === "end" || nxt == null) return;
    setPath((p) => [...p, nxt]);
  }
  function goPrev() { setWizardError(""); setPath((p) => (p.length > 1 ? p.slice(0, -1) : p)); }

  const [submitError, setSubmitError] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (collectContact && requireEmail && !contactEmail.trim()) {
      setSubmitError("Vul je e-mailadres in.");
      return;
    }
    setSubmitError("");
    const payload: AnswerPayload[] = fields
      .filter((f) => f.field_type !== "info")
      .map((f) => {
        const a = answers[f.id] || {};
        return {
          field_id: f.id,
          text: a.text ?? null,
          number: f.field_type === "number" && a.number ? Number(a.number) : null,
          option_ids: a.optionIds ?? [],
          rating: a.rating ?? null,
          other_text: a.otherText ?? null,
        };
      });
    onSubmit({
      answers: payload,
      submitter_name: collectContact ? (contactName || undefined) : undefined,
      submitter_email: collectContact ? (contactEmail || undefined) : undefined,
    });
  }

  function renderContact() {
    if (!collectContact) return null;
    return (
      <div className="border-t pt-4 space-y-3">
        <p className="font-semibold text-gray-800">Jouw gegevens</p>
        <div>
          <label className="block font-medium text-gray-800 mb-1">Naam</label>
          <input className="input w-full" value={contactName} onChange={(e) => setContactName(e.target.value)} />
        </div>
        <div>
          <label className="block font-medium text-gray-800 mb-1">
            E-mail {requireEmail && <span className="text-red-600">*</span>}
          </label>
          <input type="email" className="input w-full" value={contactEmail} required={requireEmail} onChange={(e) => setContactEmail(e.target.value)} />
        </div>
        {submitError && <div className="bg-red-50 text-red-700 rounded-lg p-2 text-sm">{submitError}</div>}
      </div>
    );
  }

  // Toont het vrije tekstvak wanneer een aangevinkte optie een "Andere…" is.
  function otherActive(f: PublicFormField, a: AnswerState): boolean {
    const selected = a.optionIds ?? [];
    return f.options.some((o) => o.is_other && selected.includes(o.id));
  }

  function renderField(f: PublicFormField) {
    const a = answers[f.id] || {};

    if (f.field_type === "info") {
      return (
        <div key={f.id}>
          {f.label && <p className="font-semibold text-gray-800">{f.label}</p>}
          {f.help_text && <p className="text-gray-600 whitespace-pre-wrap">{f.help_text}</p>}
        </div>
      );
    }

    return (
      <div key={f.id}>
        <label className="block font-medium text-gray-800 mb-1">
          {f.label} {f.required && <span className="text-red-600">*</span>}
        </label>
        {f.help_text && <p className="text-sm text-gray-500 mb-1">{f.help_text}</p>}

        {(f.field_type === "text" || f.field_type === "email" || f.field_type === "phone") && (
          <input
            type={f.field_type === "email" ? "email" : f.field_type === "phone" ? "tel" : "text"}
            className="input w-full"
            value={a.text ?? ""}
            required={f.required}
            onChange={(e) => set(f.id, { text: e.target.value })}
          />
        )}

        {f.field_type === "textarea" && (
          <textarea
            className="input w-full"
            rows={3}
            value={a.text ?? ""}
            required={f.required}
            onChange={(e) => set(f.id, { text: e.target.value })}
          />
        )}

        {f.field_type === "number" && (
          <input
            type="number"
            step="any"
            className="input w-full"
            value={a.number ?? ""}
            required={f.required}
            onChange={(e) => set(f.id, { number: e.target.value })}
          />
        )}

        {f.field_type === "select" && (
          <select
            className="input w-full"
            value={a.optionIds?.[0] ?? ""}
            required={f.required}
            onChange={(e) => toggleOption(f.id, Number(e.target.value), false)}
          >
            <option value="">— Kies —</option>
            {f.options.map((o) => (
              <option key={o.id} value={o.id}>{o.label}</option>
            ))}
          </select>
        )}

        {f.field_type === "radio" && (
          <div className="space-y-1">
            {f.options.map((o) => (
              <label key={o.id} className="flex items-center gap-2">
                <input
                  type="radio"
                  name={`field-${f.id}`}
                  checked={(a.optionIds?.[0] ?? null) === o.id}
                  onChange={() => toggleOption(f.id, o.id, false)}
                />
                {o.label}
              </label>
            ))}
          </div>
        )}

        {f.field_type === "checkbox" && (
          <div className="space-y-1">
            {f.options.map((o) => (
              <label key={o.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={a.optionIds?.includes(o.id) ?? false}
                  onChange={() => toggleOption(f.id, o.id, true)}
                />
                {o.label}
              </label>
            ))}
          </div>
        )}

        {(f.field_type === "select" || f.field_type === "radio" || f.field_type === "checkbox") &&
          otherActive(f, a) && (
            <input
              className="input w-full mt-2"
              placeholder="Andere: vul hier in…"
              value={a.otherText ?? ""}
              onChange={(e) => set(f.id, { otherText: e.target.value })}
            />
          )}

        {f.field_type === "rating" && (
          <div className="flex flex-wrap gap-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                type="button"
                key={n}
                onClick={() => set(f.id, { rating: n })}
                className={`px-3 py-1 rounded-lg border text-sm ${
                  a.rating === n ? "bg-blue-700 text-white border-blue-700" : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"
                }`}
              >
                {RATING_LABELS[n]}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Wizard: sectie-voor-sectie zodra er branching is (skip-logica navigeert).
  if (hasBranching && orderedSections.length > 0) {
    const currentSec = orderedSections.find((s) => s.id === currentId);
    const onWizardSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      if (missingRequired(stepFields)) { setWizardError("Vul de verplichte velden in."); return; }
      handleSubmit(e);
    };
    return (
      <form onSubmit={onWizardSubmit} className="space-y-6">
        {path.length === 1 && ungrouped.length > 0 && <div className="space-y-5">{ungrouped.map(renderField)}</div>}
        {currentSec && (
          <div className="space-y-4">
            {currentSec.title && <h2 className="text-lg font-bold text-blue-800">{currentSec.title}</h2>}
            {currentSec.description && <p className="text-gray-600 whitespace-pre-wrap">{currentSec.description}</p>}
            <div className="space-y-5">{currentFields.map(renderField)}</div>
          </div>
        )}
        {isLastStep && renderContact()}
        {wizardError && <div className="bg-red-50 text-red-700 rounded-lg p-2 text-sm">{wizardError}</div>}
        <div className="flex gap-2 border-t pt-4">
          {path.length > 1 && (
            <button type="button" className="btn-secondary" onClick={goPrev}>Vorige</button>
          )}
          {isLastStep ? (
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? "Bezig…" : submitLabel}
            </button>
          ) : (
            <button type="button" className="btn-primary" onClick={goNext}>Volgende</button>
          )}
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {ungrouped.length > 0 && <div className="space-y-5">{ungrouped.map(renderField)}</div>}

      {orderedSections.map((sec) => {
        const secFields = fields.filter((f) => f.section_id === sec.id);
        if (secFields.length === 0 && !sec.title && !sec.description) return null;
        return (
          <div key={sec.id} className="space-y-4 border-t pt-4">
            {sec.title && <h2 className="text-lg font-bold text-blue-800">{sec.title}</h2>}
            {sec.description && <p className="text-gray-600 whitespace-pre-wrap">{sec.description}</p>}
            <div className="space-y-5">{secFields.map(renderField)}</div>
          </div>
        );
      })}

      {renderContact()}

      <button type="submit" className="btn-primary" disabled={submitting}>
        {submitting ? "Bezig…" : submitLabel}
      </button>
    </form>
  );
}
