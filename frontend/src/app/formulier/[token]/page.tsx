"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getPublicForm, submitPublicForm } from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import type { PublicForm, AnswerPayload } from "@/lib/types";
import DynamicForm from "@/components/DynamicForm";

function deriveEmail(form: PublicForm, answers: AnswerPayload[]): string | undefined {
  const emailField = form.fields.find((f) => f.field_type === "email");
  if (!emailField) return undefined;
  const ans = answers.find((a) => a.field_id === emailField.id);
  return ans?.text || undefined;
}

export default function PublicFormPage() {
  const params = useParams();
  const token = String(params.token);
  const [form, setForm] = useState<PublicForm | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getPublicForm(token)
      .then((r) => setForm(r.data))
      .catch(() => setForm(null))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSubmit(payload: { answers: AnswerPayload[] }) {
    if (!form) return;
    setSubmitting(true);
    setError("");
    try {
      await submitPublicForm(token, {
        submitter_email: deriveEmail(form, payload.answers),
        answers: payload.answers,
      });
      setDone(true);
    } catch (e) {
      setError(parseApiError(e, "Versturen mislukt."));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="max-w-2xl mx-auto p-4">Laden…</div>;
  if (!form) return <div className="max-w-2xl mx-auto p-4"><div className="card">Dit formulier bestaat niet of is niet (meer) beschikbaar.</div></div>;

  return (
    <div className="max-w-2xl mx-auto p-4">
      <div className="card">
        <h1 className="text-2xl font-bold text-blue-800 mb-2">{form.title}</h1>
        {form.description && <p className="text-gray-700 whitespace-pre-wrap mb-4">{form.description}</p>}

        {done ? (
          <div className="bg-green-50 text-green-800 rounded-lg p-4">Bedankt! Je antwoord is goed ontvangen.</div>
        ) : form.status !== "open" ? (
          <div className="bg-amber-50 text-amber-800 rounded-lg p-4">Dit formulier is gesloten en neemt geen inzendingen meer aan.</div>
        ) : (
          <>
            {error && <div className="bg-red-50 text-red-700 rounded-lg p-3 mb-3 text-sm">{error}</div>}
            <DynamicForm fields={form.fields} sections={form.sections} submitting={submitting} onSubmit={handleSubmit} />
          </>
        )}
      </div>
    </div>
  );
}
