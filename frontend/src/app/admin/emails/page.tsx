"use client";
import { useEffect, useState } from "react";
import { getEmailLog } from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import { sanitizeCmsHtml } from "@/lib/sanitize";
import type { EmailLogItem } from "@/lib/types";

const STATUS_BADGE: Record<string, string> = {
  sent: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  skipped: "bg-gray-100 text-gray-600",
};

const TYPE_LABELS: Record<string, string> = {
  membership_confirmation: "Lidmaatschap",
  activity_confirmation: "Activiteit",
  idea_ack: "Idee (bevestiging)",
  idea_board: "Idee (bestuur)",
  magic_link: "Inloglink",
  member_contact_notice: "Contactmelding",
  form_confirmation: "Formulier",
  other: "Overig",
};

export default function AdminEmails() {
  const [items, setItems] = useState<EmailLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<EmailLogItem | null>(null);
  const [error, setError] = useState("");
  const perPage = 50;

  function load() {
    getEmailLog({
      status: statusFilter || undefined,
      email_type: typeFilter || undefined,
      recipient: search || undefined,
      page,
      per_page: perPage,
    })
      .then((r) => {
        setItems(r.data.items);
        setTotal(r.data.total);
      })
      .catch((e) => setError(parseApiError(e, "Laden mislukt.")));
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [page, statusFilter, typeFilter]);

  const pages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div>
      <h1 className="text-2xl font-bold text-blue-800 mb-1">Verstuurde e-mails</h1>
      <p className="text-gray-500 text-sm mb-4">Alle uitgaande mails worden hier gelogd (bevat persoonsgegevens — admin-only).</p>

      <div className="flex flex-wrap gap-2 mb-4 items-end">
        <select className="input" value={typeFilter} onChange={(e) => { setPage(1); setTypeFilter(e.target.value); }}>
          <option value="">Alle types</option>
          {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="input" value={statusFilter} onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }}>
          <option value="">Alle statussen</option>
          <option value="sent">Verstuurd</option>
          <option value="failed">Mislukt</option>
          <option value="skipped">Overgeslagen</option>
        </select>
        <form onSubmit={(e) => { e.preventDefault(); setPage(1); load(); }} className="flex gap-2">
          <input className="input" placeholder="Zoek op ontvanger" value={search} onChange={(e) => setSearch(e.target.value)} />
          <button className="btn-secondary btn-sm" type="submit">Zoek</button>
        </form>
      </div>

      {error && <div className="bg-red-50 text-red-700 rounded-lg p-3 mb-3 text-sm">{error}</div>}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="py-2 pr-3">Tijdstip</th>
              <th className="py-2 pr-3">Ontvanger</th>
              <th className="py-2 pr-3">Type</th>
              <th className="py-2 pr-3">Onderwerp</th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id} className="border-b last:border-0">
                <td className="py-2 pr-3 whitespace-nowrap text-gray-600">{new Date(it.created_at).toLocaleString("nl-BE")}</td>
                <td className="py-2 pr-3">{it.recipient}</td>
                <td className="py-2 pr-3">{TYPE_LABELS[it.email_type] ?? it.email_type}</td>
                <td className="py-2 pr-3">{it.subject}</td>
                <td className="py-2 pr-3"><span className={`text-xs px-2 py-1 rounded-full ${STATUS_BADGE[it.status] ?? ""}`}>{it.status}</span></td>
                <td className="py-2"><button className="text-blue-700 hover:underline" onClick={() => setOpen(it)}>Bekijk</button></td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="py-4 text-gray-500">Geen mails gevonden.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-3 text-sm">
        <span className="text-gray-500">{total} mails</span>
        <div className="flex gap-2">
          <button className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Vorige</button>
          <span className="px-2 py-1">{page} / {pages}</span>
          <button className="btn-secondary btn-sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Volgende</button>
        </div>
      </div>

      {open && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50" onClick={() => setOpen(null)}>
          <div className="bg-white rounded-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-start mb-3">
              <h2 className="text-lg font-bold">{open.subject}</h2>
              <button className="text-gray-500" onClick={() => setOpen(null)}>✕</button>
            </div>
            <p className="text-sm text-gray-600 mb-1">Aan: {open.recipient}</p>
            <p className="text-sm text-gray-600 mb-3">Status: {open.status}{open.error_message ? ` — ${open.error_message}` : ""}</p>
            {/* Herstel de mail-typografie die Tailwind's reset wegneemt: bullets/
                indent bij lijsten, blauwe onderstreepte links, koppen, blockquote
                en afbreken van lange URL's — zodat de preview toont zoals de
                ontvanger de mail ziet. */}
            <style>{`
              .email-body { overflow-wrap: anywhere; word-break: break-word; line-height: 1.5; }
              .email-body p { margin: 0.5rem 0; }
              .email-body h1,.email-body h2,.email-body h3,.email-body h4 { font-weight: 600; margin: 0.7rem 0 0.25rem; }
              .email-body ul { list-style: disc; padding-left: 1.5rem; margin: 0.4rem 0; }
              .email-body ol { list-style: decimal; padding-left: 1.5rem; margin: 0.4rem 0; }
              .email-body li { margin: 0.15rem 0; }
              .email-body a { color: #1d4ed8; text-decoration: underline; overflow-wrap: anywhere; }
              .email-body blockquote { border-left: 4px solid #ccc; padding-left: 12px; color: #555; margin: 0.5rem 0; }
            `}</style>
            <div className="email-body border rounded-lg p-3 text-sm" dangerouslySetInnerHTML={{ __html: sanitizeCmsHtml(open.body ?? "") }} />
          </div>
        </div>
      )}
    </div>
  );
}
