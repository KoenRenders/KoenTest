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
  onSubmit,
}: {
  fields: PublicFormField[];
  sections?: FormSection[];
  initial?: DynamicFormInitial;
  submitting?: boolean;
  submitLabel?: string;
  onSubmit: (payload: { answers: AnswerPayload[] }) => void;
}) {
  const [answers, setAnswers] = useState<Record<number, AnswerState>>(() => buildInitial(fields, initial));

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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
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
    onSubmit({ answers: payload });
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

        {(f.field_type === "text" || f.field_type === "email") && (
          <input
            type={f.field_type === "email" ? "email" : "text"}
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

  const orderedSections = [...(sections ?? [])].sort((s1, s2) => s1.position - s2.position);
  const ungrouped = fields.filter((f) => f.section_id == null);

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

      <button type="submit" className="btn-primary" disabled={submitting}>
        {submitting ? "Bezig…" : submitLabel}
      </button>
    </form>
  );
}
