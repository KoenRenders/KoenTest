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

function PrintField({ field, sectionLabel }: { field: FormFieldDef; sectionLabel: (id: number) => string }) {
  const { field_type: t } = field;
  const routeText = (o: { skip_to_section_id?: number | null; skip_to_end?: boolean }): string => {
    if (o.skip_to_end) return "→ einde";
    if (o.skip_to_section_id != null) return `→ ga naar ${sectionLabel(o.skip_to_section_id)}`;
    return "";
  };

  if (t === "info") {
    return (
      <div className="mb-4 break-inside-avoid">
        {field.label && <p className="font-semibold text-gray-900">{field.label}</p>}
        {field.help_text && <p className="text-gray-700 whitespace-pre-wrap">{field.help_text}</p>}
      </div>
    );
  }

  return (
    <div className="mb-5 break-inside-avoid">
      <div className="font-medium text-gray-900">
        {field.label} {field.required && <span>*</span>}
      </div>
      {field.help_text && <div className="text-sm text-gray-500">{field.help_text}</div>}

      {(t === "text" || t === "email" || t === "number" || t === "phone") && <Lines n={1} />}
      {t === "textarea" && <Lines n={3} />}

      {(t === "select" || t === "radio" || t === "checkbox") && (
        <div className="mt-2 space-y-1">
          {field.options.map((o) => (
            <div key={o.id} className="flex items-center">
              <Box />
              <span>{o.label}</span>
              {o.is_other && <span className="flex-1 border-b border-gray-400 mx-2 self-end" />}
              {(t === "radio" || t === "select") && routeText(o) && (
                <span className="text-gray-500 italic ml-2 whitespace-nowrap">{routeText(o)}</span>
              )}
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

  const orderedSecs = [...form.sections].sort((a, b) => a.position - b.position);
  const secLabelById: Record<number, string> = {};
  orderedSecs.forEach((s, i) => { secLabelById[s.id] = s.title || `Sectie ${i + 1}`; });
  const sectionLabel = (id: number) => secLabelById[id] ?? "een sectie";
  const nextText = (sec: FormAdmin["sections"][number]): string => {
    if (sec.next_is_end) return "→ Ga daarna naar het einde.";
    if (sec.next_section_id != null) return `→ Ga daarna naar ${sectionLabel(sec.next_section_id)}.`;
    return "";
  };

  return (
    <div>
      {/* Print-CSS: verberg de admin-sidebar en alle knoppen bij het afdrukken. */}
      <style>{`
        @media print {
          /* Verberg admin-chrome én de site-footer (sociale media, sponsorlogo,
             onze gegevens) en het raakje-chatbubbeltje (fixed) op de afdruk. */
          aside, .no-print, footer, .fixed { display: none !important; }
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

        {form.fields.filter((f) => f.section_id == null).map((f) => <PrintField key={f.id} field={f} sectionLabel={sectionLabel} />)}

        {orderedSecs.map((sec) => {
          const secFields = form.fields.filter((f) => f.section_id === sec.id);
          if (secFields.length === 0 && !sec.title && !sec.description) return null;
          return (
            <div key={sec.id} className="mt-6 pt-4 border-t border-gray-300 break-inside-avoid">
              {sec.title && <h3 className="text-lg font-bold text-gray-900 mb-1">{sec.title}</h3>}
              {sec.description && <p className="text-gray-700 whitespace-pre-wrap mb-3">{sec.description}</p>}
              {secFields.map((f) => <PrintField key={f.id} field={f} sectionLabel={sectionLabel} />)}
              {nextText(sec) && <p className="text-gray-500 italic mt-2">{nextText(sec)}</p>}
            </div>
          );
        })}

        <div className="mt-8 pt-4 border-t border-gray-300 grid grid-cols-2 gap-6 text-sm text-gray-600">
          <div>Naam: <span className="inline-block border-b border-gray-400 w-40 align-bottom" /></div>
          <div>Datum: <span className="inline-block border-b border-gray-400 w-32 align-bottom" /></div>
          {!form.is_anonymous && <div className="col-span-2">E-mail: <span className="inline-block border-b border-gray-400 w-64 align-bottom" /></div>}
        </div>
      </div>
    </div>
  );
}
