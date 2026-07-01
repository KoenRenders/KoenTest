"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getForm } from "@/lib/api";
import type { FormAdmin, FormFieldDef } from "@/lib/types";

const RATING_LABELS = ["Zeer slecht", "Slecht", "Neutraal", "Goed", "Zeer goed"];

function Lines({ n }: { n: number }) {
  return (
    <div className="mt-1 space-y-4">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="border-b border-gray-400" />
      ))}
    </div>
  );
}

function Box() {
  return <span className="inline-block w-4 h-4 border border-gray-500 mr-2 align-middle" />;
}

function PrintField({ field }: { field: FormFieldDef }) {
  const { field_type: t } = field;
  return (
    <div className="mb-5 break-inside-avoid">
      <div className="font-medium text-gray-900">
        {field.label} {field.required && <span>*</span>}
      </div>
      {field.help_text && <div className="text-sm text-gray-500">{field.help_text}</div>}

      {(t === "text" || t === "email" || t === "number") && <Lines n={1} />}
      {t === "textarea" && <Lines n={3} />}

      {(t === "select" || t === "radio" || t === "checkbox") && (
        <div className="mt-2 space-y-1">
          {field.options.map((o) => (
            <div key={o.id} className="flex items-center">
              <Box />
              <span>{o.label}</span>
            </div>
          ))}
          {field.options.length === 0 && <Lines n={1} />}
        </div>
      )}

      {t === "rating" && (
        <div className="mt-2 flex flex-wrap gap-4">
          {RATING_LABELS.map((label, i) => (
            <span key={i} className="flex items-center">
              <Box />
              <span>{label}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function FormPrintPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  const [form, setForm] = useState<FormAdmin | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getForm(id)
      .then((r) => setForm(r.data))
      .catch(() => setForm(null))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div>Laden…</div>;
  if (!form) return <div className="card">Formulier niet gevonden.</div>;

  return (
    <div>
      {/* Print-CSS: verberg de admin-sidebar en alle knoppen bij het afdrukken. */}
      <style>{`
        @media print {
          aside, .no-print { display: none !important; }
          .print-sheet { box-shadow: none !important; border: none !important; padding: 0 !important; }
          body { background: white !important; }
        }
      `}</style>

      <div className="no-print flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-blue-800">Afdrukvoorbeeld</h1>
        <div className="flex gap-2">
          <button className="btn-secondary btn-sm" onClick={() => router.push("/admin/formulieren")}>Terug</button>
          <button className="btn-primary btn-sm" onClick={() => window.print()}>Afdrukken</button>
        </div>
      </div>

      <div className="card print-sheet max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold mb-2">{form.title}</h2>
        {form.description && <p className="text-gray-700 whitespace-pre-wrap mb-5">{form.description}</p>}

        {form.fields.map((f) => <PrintField key={f.id} field={f} />)}

        <div className="mt-8 pt-4 border-t border-gray-300 grid grid-cols-2 gap-6 text-sm text-gray-600">
          <div>Naam: <span className="inline-block border-b border-gray-400 w-40 align-bottom" /></div>
          <div>Datum: <span className="inline-block border-b border-gray-400 w-32 align-bottom" /></div>
        </div>
      </div>
    </div>
  );
}
