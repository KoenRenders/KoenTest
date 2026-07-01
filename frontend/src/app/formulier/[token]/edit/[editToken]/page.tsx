"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getEditableSubmission, updateSubmission } from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import type { PublicForm, AnswerPayload } from "@/lib/types";
import DynamicForm, { type DynamicFormInitial } from "@/components/DynamicForm";

function deriveEmail(form: PublicForm, answers: AnswerPayload[]): string | undefined {
  const emailField = form.fields.find((f) => f.field_type === "email");
  if (!emailField) return undefined;
  const ans = answers.find((a) => a.field_id === emailField.id);
  return ans?.text || undefined;
}

export default function EditSubmissionPage() {
  const params = useParams();
  const editToken = String(params.editToken);
  const [form, setForm] = useState<PublicForm | null>(null);
  const [initial, setInitial] = useState<DynamicFormInitial | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getEditableSubmission(editToken)
      .then((r) => {
        setForm(r.data.form);
        setInitial({
          submitter_name: r.data.submitter_name,
          submitter_email: r.data.submitter_email,
          answers: r.data.answers,
        });
      })
      .catch(() => setForm(null))
      .finally(() => setLoading(false));
  }, [editToken]);

  async function handleSubmit(payload: { answers: AnswerPayload[] }) {
    if (!form) return;
    setSubmitting(true);
    setError("");
    try {
      await updateSubmission(editToken, {
        submitter_email: deriveEmail(form, payload.answers),
        answers: payload.answers,
      });
      setDone(true);
    } catch (e) {
      setError(parseApiError(e, "Opslaan mislukt."));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="max-w-2xl mx-auto p-4">Laden…</div>;
  if (!form || !initial) return <div className="max-w-2xl mx-auto p-4"><div className="card">Deze wijzig-link is ongeldig of verlopen.</div></div>;

  return (
    <div className="max-w-2xl mx-auto p-4">
      <div className="card">
        <h1 className="text-2xl font-bold text-blue-800 mb-2">{form.title}</h1>
        <p className="text-gray-600 text-sm mb-4">Je past hier je eerdere antwoord aan.</p>
        {done ? (
          <div className="bg-green-50 text-green-800 rounded-lg p-4">Je aanpassing is opgeslagen.</div>
        ) : form.status !== "open" ? (
          <div className="bg-amber-50 text-amber-800 rounded-lg p-4">Dit formulier is gesloten; aanpassen kan niet meer.</div>
        ) : (
          <>
            {error && <div className="bg-red-50 text-red-700 rounded-lg p-3 mb-3 text-sm">{error}</div>}
            <DynamicForm fields={form.fields} sections={form.sections} initial={initial} submitting={submitting} submitLabel="Aanpassing opslaan" onSubmit={handleSubmit} />
          </>
        )}
      </div>
    </div>
  );
}
