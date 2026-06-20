"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { listPaymentRecords, updatePaymentRecord, refreshPaymentRecord, refundPaymentRecord, deletePaymentRecord, getRegistrations, getAuthMe, exportPaymentsOds } from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import { matchesPaymentFilter } from "@/lib/paymentFilters";
import RegistrationList, { type RegistrationEntry } from "@/components/RegistrationList";

interface RegItem {
  product_name: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
}

interface PaymentRecord {
  id: string;
  payable_type: string;
  payable_id: number;
  amount: string;
  amount_paid: string | null;
  activity_id: number | null;
  component_id: number | null;
  component_name: string | null;
  items: RegItem[];
  method: string;
  status: string;
  type: string;             // "charge" | "refund" (#83)
  refund_of_id: string | null;
  note: string | null;
  paid_at: string | null;
  structured_communication: string | null;  // OGM voor overschrijving (#224)
  created_at: string;
  description: string | null;
  contact_name: string | null;
  membership_year: number | null;  // lidgeld-jaar voor de jaarfilter (#308)
}

const STATUS_LABELS: Record<string, string> = {
  pending: "In afwachting",
  paid: "Betaald",
  failed: "Mislukt",
  cancelled: "Geannuleerd",
};

const METHOD_LABELS: Record<string, string> = {
  online: "Online",
  transfer: "Overschrijving",
  cash: "Cash",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  paid: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-500",
};

const PAYABLE_LABELS: Record<string, string> = {
  registration: "Inschrijving",
  membership: "Lidmaatschap",
};

export default function BetalingenPage() {
  const [records, setRecords] = useState<PaymentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  // Enkel FINANCE mag betalingen muteren; ADMIN ziet alles read-only (#207).
  const [canEdit, setCanEdit] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [editData, setEditData] = useState<{ amount_paid: string; note: string; status: string }>({
    amount_paid: "",
    note: "",
    status: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "openstaand" | "pending" | "paid">("all");
  // Context-filter (#90): "all" | "membership" | "comp-<id>"
  const [context, setContext] = useState<string>("all");
  // Lidgeld-jaar-filter (#308): null = alle jaren.
  const [year, setYear] = useState<number | null>(null);

  // Terugbetaling registreren (#83): record id -> formulier
  const [refunding, setRefunding] = useState<string | null>(null);
  const [refundData, setRefundData] = useState<{ amount: string; note: string }>({ amount: "", note: "" });
  const [refundSaving, setRefundSaving] = useState(false);
  const [refundError, setRefundError] = useState<string | null>(null);

  // Registration details: record id -> RegistrationEntry | null (null = loading)
  const [regDetails, setRegDetails] = useState<Record<string, RegistrationEntry | null>>({});

  // Welke OGM net gekopieerd is (voor "gekopieerd ✓"-feedback).
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Kopiëren dat óók over HTTP werkt: de Clipboard-API vereist een secure context
  // (HTTPS/localhost); valt die weg, dan via een tijdelijke textarea + execCommand (#224).
  async function copyOgm(id: string, text: string) {
    let ok = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        ok = true;
      }
    } catch { /* val terug op execCommand */ }
    if (!ok) {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        ok = document.execCommand("copy");
        document.body.removeChild(ta);
      } catch { ok = false; }
    }
    if (ok) {
      setCopiedId(id);
      setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1500);
    } else {
      alert("Kopiëren lukte niet — selecteer de mededeling en kopieer ze handmatig.");
    }
  }

  async function load() {
    try {
      const resp = await listPaymentRecords();
      setRecords(resp.data);
      setError(null);
    } catch (e) {
      setError(parseApiError(e, "Kon de betalingen niet laden."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);
  useEffect(() => {
    getAuthMe().then((r) => setCanEdit(r.data.is_finance)).catch(() => setCanEdit(false));
  }, []);

  async function loadRegDetails(record: PaymentRecord) {
    if (!record.activity_id || record.payable_type !== "registration") return;
    setRegDetails((prev) => ({ ...prev, [record.id]: null }));
    try {
      const resp = await getRegistrations(record.activity_id);
      const reg = resp.data.find((r: { id: number }) => r.id === record.payable_id);
      if (!reg) {
        setRegDetails((prev) => { const next = { ...prev }; delete next[record.id]; return next; });
        return;
      }
      const entry: RegistrationEntry = {
        contact_name: reg.contact_name,
        contact_email: reg.contact_email,
        phone: reg.phone,
        team_name: reg.team_name,
        payment_method: reg.payment_method,
        remarks: reg.remarks,
        items: record.items.map((it) => ({
          product_name: it.product_name,
          quantity: it.quantity,
          subtotal: it.subtotal,
        })),
      };
      setRegDetails((prev) => ({ ...prev, [record.id]: entry }));
    } catch {
      setRegDetails((prev) => { const next = { ...prev }; delete next[record.id]; return next; });
    }
  }

  function toggleRegDetails(record: PaymentRecord) {
    if (record.id in regDetails) {
      setRegDetails((prev) => { const next = { ...prev }; delete next[record.id]; return next; });
    } else {
      loadRegDetails(record);
    }
  }

  function startEdit(r: PaymentRecord) {
    setEditing(r.id);
    setEditError(null);
    setEditData({
      amount_paid: r.amount_paid ?? "",
      note: r.note ?? "",
      status: r.status,
    });
  }

  async function saveEdit(id: string) {
    setSaving(true);
    setEditError(null);
    try {
      await updatePaymentRecord(id, {
        status: editData.status || undefined,
        amount_paid: editData.amount_paid ? parseFloat(editData.amount_paid) : undefined,
        note: editData.note || undefined,
      });
      setEditing(null);
      await load();
    } catch (e) {
      setEditError(parseApiError(e, "Opslaan mislukt. Controleer de ingevoerde waarden."));
    } finally {
      setSaving(false);
    }
  }

  function startRefund(r: PaymentRecord) {
    setRefunding(r.id);
    setRefundError(null);
    setRefundData({ amount: "", note: "" });
  }

  async function saveRefund(id: string) {
    const amount = parseFloat(refundData.amount);
    if (!amount || amount <= 0) {
      setRefundError("Geef een terug te betalen bedrag op (groter dan 0).");
      return;
    }
    setRefundSaving(true);
    setRefundError(null);
    try {
      await refundPaymentRecord(id, { amount, note: refundData.note || undefined });
      setRefunding(null);
      await load();
    } catch (e) {
      setRefundError(parseApiError(e, "Terugbetaling registreren mislukt."));
    } finally {
      setRefundSaving(false);
    }
  }

  async function downloadPaymentsExport() {
    try {
      const resp = await exportPaymentsOds();
      const url = URL.createObjectURL(resp.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "betalingen-en-vorderingen.ods";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(parseApiError(e, "Export mislukt."));
    }
  }

  async function refreshStatus(id: string) {
    setRefreshing(id);
    setError(null);
    try {
      await refreshPaymentRecord(id);
      await load();
    } catch (e) {
      setError(parseApiError(e, "Status verversen mislukt."));
    } finally {
      setRefreshing(null);
    }
  }

  async function removePayment(r: PaymentRecord) {
    const label = r.contact_name || r.description || "deze betaling";
    if (!confirm(`Betaling van "${label}" definitief verwijderen? Het feit blijft in de audit-historie bewaard.`)) return;
    setError(null);
    try {
      await deletePaymentRecord(r.id);
      await load();
    } catch (e) {
      setError(parseApiError(e, "Betaling verwijderen mislukt."));
    }
  }

  function saldo(r: PaymentRecord) {
    return parseFloat(r.amount) - (r.amount_paid ? parseFloat(r.amount_paid) : 0);
  }

  // Betaald/openstaand wordt afgeleid uit het saldo (betaald = waarheid), niet uit de
  // status-badge (#198). Mislukt/geannuleerd komen nog van de online/Mollie-status.
  function paymentState(r: PaymentRecord): { label: string; cls: string } {
    if (r.status === "failed") return { label: "Mislukt", cls: STATUS_COLORS["failed"] ?? "bg-red-100 text-red-700" };
    if (r.status === "cancelled") return { label: "Geannuleerd", cls: STATUS_COLORS["cancelled"] ?? "bg-gray-100 text-gray-600" };
    const s = saldo(r);
    if (Math.abs(s) < 0.005) return { label: "Vereffend", cls: "bg-green-100 text-green-700" };
    if (s > 0) return { label: "Openstaand", cls: "bg-amber-100 text-amber-800" };
    return { label: "Terug te betalen", cls: "bg-orange-100 text-orange-700" };
  }

  // Filter-logica zit als puur predicaat in @/lib/paymentFilters (Vitest-gedekt, #308).
  const filtered = records.filter((r) => matchesPaymentFilter(r, { status: filter, context, year }));

  // Lidgeld-jaren aanwezig in de records, aflopend — voedt de jaar-dropdown (#308).
  const membershipYears = Array.from(
    new Set(records.map((r) => r.membership_year).filter((y): y is number => y != null)),
  ).sort((a, b) => b - a);

  // Opties voor het context-filter, afgeleid uit de records: één optgroup per
  // activiteit met haar onderdelen (zoals de Media-bibliotheek), plus lidmaatschap.
  const hasMembership = records.some((r) => r.payable_type === "membership");
  const activityGroups = (() => {
    const byActivity = new Map<number, { name: string; comps: Map<number, string> }>();
    for (const r of records) {
      if (r.payable_type !== "registration" || r.activity_id == null || r.component_id == null) continue;
      const g = byActivity.get(r.activity_id) ?? { name: r.description ?? `Activiteit ${r.activity_id}`, comps: new Map() };
      g.comps.set(r.component_id, r.component_name ?? `Onderdeel ${r.component_id}`);
      byActivity.set(r.activity_id, g);
    }
    return Array.from(byActivity.entries()).map(([activityId, g]) => ({
      activityId,
      activityName: g.name,
      components: Array.from(g.comps.entries()).map(([id, name]) => ({ id, name })),
    }));
  })();

  const totalExpected = filtered.reduce((s, r) => s + parseFloat(r.amount), 0);
  const totalPaid = filtered.reduce((s, r) => s + (r.amount_paid ? parseFloat(r.amount_paid) : 0), 0);
  const totalSaldo = totalExpected - totalPaid;
  // Terugbetalingen zijn negatieve records; toon het teruggestorte bedrag positief (#83).
  const totalRefunded = filtered.reduce(
    (s, r) => s + (r.type === "refund" && r.amount_paid ? -parseFloat(r.amount_paid) : 0),
    0,
  );

  // Bundel alle betalingen/refunds van dezelfde inschrijving (payable) in één groep,
  // gesorteerd op de datum van de laatst aangemaakte betaling (#204).
  const groups = (() => {
    const map = new Map<string, PaymentRecord[]>();
    for (const r of filtered) {
      const key = `${r.payable_type}:${r.payable_id}`;
      const arr = map.get(key);
      if (arr) arr.push(r); else map.set(key, [r]);
    }
    const out = Array.from(map.values()).map((recs) => {
      const sorted = [...recs].sort((a, b) => a.created_at.localeCompare(b.created_at));
      const latest = sorted.reduce((m, r) => (r.created_at > m ? r.created_at : m), sorted[0].created_at);
      return { recs: sorted, latest, head: sorted[0] };
    });
    out.sort((a, b) => b.latest.localeCompare(a.latest));
    return out;
  })();

  if (loading) return <p className="p-8 text-gray-500">Laden…</p>;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Betalingen</h1>

      {!canEdit && (
        <p className="mb-4 rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-sm text-blue-800">
          Alleen-lezen: enkel de penningmeester (rol FINANCE) kan betalingen invullen, bewerken of terugbetalen.
        </p>
      )}

      <div className="flex gap-2 mb-4 flex-wrap items-center">
        {(["all", "openstaand", "pending", "paid"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium border transition ${
              filter === f
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
            }`}
          >
            {f === "all" ? "Alle" : f === "openstaand" ? "Openstaand saldo" : f === "pending" ? "In afwachting" : "Betaald"}
          </button>
        ))}
        <button
          onClick={downloadPaymentsExport}
          className="ml-auto px-4 py-1.5 rounded-full text-sm font-medium border bg-white text-gray-700 border-gray-300 hover:bg-gray-50 transition"
          title="Export (.ods): alle betalingen & vorderingen + totalen (te betalen / betaald / saldo)"
        >
          Export .ods
        </button>
      </div>

      {/* Context- (#90) en lidgeld-jaar-filter (#308) */}
      <div className="mb-6 flex gap-2 flex-wrap">
        {membershipYears.length > 0 && (
          <select
            className="input text-sm max-w-[10rem]"
            value={year ?? "all"}
            onChange={(e) => setYear(e.target.value === "all" ? null : parseInt(e.target.value, 10))}
            title="Filter op lidgeld-jaar"
          >
            <option value="all">Alle lidgeld-jaren</option>
            {membershipYears.map((y) => (
              <option key={y} value={y}>Lidgeld {y}</option>
            ))}
          </select>
        )}
        <select
          className="input text-sm max-w-md"
          value={context}
          onChange={(e) => setContext(e.target.value)}
        >
          <option value="all">Alle contexten</option>
          {hasMembership && <option value="membership">Lidmaatschap-vernieuwing</option>}
          {activityGroups.map((g) => (
            <optgroup key={g.activityId} label={g.activityName}>
              {g.components.map((c) => (
                <option key={c.id} value={`comp-${c.id}`}>{c.name}</option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {error && (
        <p className="mb-4 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-3">{error}</p>
      )}

      <div className="flex gap-6 mb-6 text-sm text-gray-600 flex-wrap">
        <span>{filtered.length} betaling{filtered.length !== 1 ? "en" : ""}</span>
        <span>Verwacht: <strong>€{totalExpected.toFixed(2)}</strong></span>
        <span>Ontvangen: <strong>€{totalPaid.toFixed(2)}</strong></span>
        {totalRefunded > 0.001 && (
          <span className="text-orange-600">Terugbetaald: <strong>€{totalRefunded.toFixed(2)}</strong></span>
        )}
        <span className={totalSaldo > 0.001 ? "text-red-600 font-semibold" : "text-green-600 font-semibold"}>
          Saldo: €{totalSaldo.toFixed(2)}
        </span>
      </div>

      {filtered.length === 0 ? (
        <p className="text-gray-500 italic">Geen betalingen gevonden.</p>
      ) : (
        <div className="space-y-3">
          {groups.map((g) => (
            <div
              key={`${g.head.payable_type}:${g.head.payable_id}`}
              className={g.recs.length > 1 ? "rounded-xl border border-blue-200 bg-blue-50/40 p-2 space-y-2" : ""}
            >
              {g.recs.map((r) => (
            <div key={r.id} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-gray-900 truncate">
                      {r.contact_name || "—"}
                    </span>
                    <span className="text-gray-400">·</span>
                    <span className="text-sm text-gray-600">
                      {r.description || PAYABLE_LABELS[r.payable_type] || r.payable_type}
                      {r.component_name && (
                        <span className="text-gray-500"> · {r.component_name}</span>
                      )}
                    </span>
                    {(() => { const st = paymentState(r); return (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${st.cls}`}>
                        {st.label}
                      </span>
                    ); })()}
                    {r.type === "refund" && (
                      <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-orange-100 text-orange-700">
                        Terugbetaling
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-sm text-gray-500 flex gap-4 flex-wrap">
                    <span>{METHOD_LABELS[r.method] ?? r.method}</span>
                    <span>Bedrag: €{parseFloat(r.amount).toFixed(2)}</span>
                    {r.amount_paid && (
                      <span className="text-green-700">Ontvangen: €{parseFloat(r.amount_paid).toFixed(2)}</span>
                    )}
                    {(() => { const s = saldo(r); return s > 0.001 ? (
                      <span className="text-red-600 font-medium">Saldo: €{s.toFixed(2)}</span>
                    ) : s <= 0 && r.amount_paid ? (
                      <span className="text-green-600 font-medium">Saldo: €0.00</span>
                    ) : null; })()}
                    {r.paid_at && (
                      <span>Betaald op: {new Date(r.paid_at).toLocaleDateString("nl-BE")}</span>
                    )}
                  </div>
                  {r.note && (
                    <p className="mt-1 text-sm text-gray-500 italic">{r.note}</p>
                  )}
                  {/* Gestructureerde mededeling (OGM) — voor manueel afboeken van een
                      overschrijving op het rekeninguittreksel (#224). */}
                  {r.structured_communication && (
                    <div className="mt-1 flex items-center gap-2 text-sm flex-wrap">
                      <span className="text-gray-500">Mededeling:</span>
                      <code className="font-mono text-gray-800 bg-gray-100 rounded px-1.5 py-0.5">
                        {r.structured_communication}
                      </code>
                      <button
                        type="button"
                        onClick={() => copyOgm(r.id, r.structured_communication!)}
                        className="text-xs text-blue-600 hover:underline"
                        title="Kopieer de gestructureerde mededeling"
                      >
                        {copiedId === r.id ? "gekopieerd ✓" : "kopieer"}
                      </button>
                    </div>
                  )}

                  {/* Registration details (on-demand) */}
                  {r.payable_type === "registration" && r.activity_id && (
                    <div className="mt-2">
                      <button
                        className="text-xs text-blue-600 hover:underline"
                        onClick={() => toggleRegDetails(r)}
                      >
                        {r.id in regDetails ? "Verberg details" : "Toon inschrijvingsdetails"}
                      </button>
                      {r.id in regDetails && (
                        <div className="mt-2 border-t border-gray-100 pt-2">
                          {regDetails[r.id] === null ? (
                            <p className="text-xs text-gray-400">Laden…</p>
                          ) : (
                            <RegistrationList entries={[regDetails[r.id]!]} />
                          )}
                          {/* Deep-link naar het bestelregel-scherm van net deze inschrijving (#187). */}
                          <Link
                            href={`/admin/activiteiten?activity=${r.activity_id}${r.component_id ? `&component=${r.component_id}` : ""}&reg=${r.payable_id}&from=betalingen`}
                            className="text-xs text-blue-600 hover:underline mt-2 inline-block"
                          >
                            Bestelregels bewerken in Activiteiten →
                          </Link>
                        </div>
                      )}
                    </div>
                  )}
                </div>
                {canEdit && editing !== r.id && refunding !== r.id && (
                  <div className="flex flex-col gap-1 items-end">
                    <button
                      onClick={() => startEdit(r)}
                      className="text-xs text-blue-600 border border-blue-200 rounded px-2 py-0.5 hover:bg-blue-50 whitespace-nowrap"
                    >
                      Bewerken
                    </button>
                    {r.method === "online" && (
                      <button
                        onClick={() => refreshStatus(r.id)}
                        disabled={refreshing === r.id}
                        className="text-xs text-gray-600 border border-gray-200 rounded px-2 py-0.5 hover:bg-gray-50 whitespace-nowrap disabled:opacity-50"
                        title="Haal de actuele betaalstatus bij Mollie op"
                      >
                        {refreshing === r.id ? "Verversen…" : "Status verversen"}
                      </button>
                    )}
                    {/* Terugbetalen kan enkel op een charge waar geld op ontvangen is (#83) */}
                    {r.type !== "refund" && r.amount_paid && parseFloat(r.amount_paid) > 0 && (
                      <button
                        onClick={() => startRefund(r)}
                        className="text-xs text-orange-600 border border-orange-200 rounded px-2 py-0.5 hover:bg-orange-50 whitespace-nowrap"
                      >
                        Terugbetaling registreren
                      </button>
                    )}
                    {/* Verwijderen kan niet als er geld bewoog: Mollie-betaald of een
                        ontvangen/betaald bedrag (#218) — corrigeer via terugbetaling. */}
                    {!((r.method === "online" && r.status === "paid")
                       || (r.amount_paid != null && parseFloat(r.amount_paid) !== 0)) && (
                      <button
                        onClick={() => removePayment(r)}
                        className="text-xs text-red-600 border border-red-200 rounded px-2 py-0.5 hover:bg-red-50 whitespace-nowrap"
                        title="Betaling verwijderen (blijft in audit-historie)"
                      >
                        Verwijderen
                      </button>
                    )}
                  </div>
                )}
              </div>

              {editing === r.id && (
                <div className="mt-3 pt-3 border-t border-gray-100 space-y-3">
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                      <select
                        className="input text-sm"
                        value={editData.status}
                        onChange={(e) => {
                          const status = e.target.value;
                          // Bij 'Betaald' meteen het volledige (verschuldigde resp. terug te
                          // betalen) bedrag voorvullen als nog leeg (#199); de penningmeester kan
                          // het nog corrigeren (bv. op 0 zetten, #222).
                          setEditData((d) => ({
                            ...d,
                            status,
                            amount_paid: status === "paid" && !d.amount_paid
                              ? parseFloat(r.amount).toFixed(2) : d.amount_paid,
                          }));
                        }}
                      >
                        <option value="pending">In afwachting</option>
                        <option value="paid">Betaald</option>
                        <option value="failed">Mislukt</option>
                        <option value="cancelled">Geannuleerd</option>
                      </select>
                    </div>
                    {/* Bedrag blijft corrigeerbaar (#222): bij een refund is het negatief
                        (max 0), bij een charge positief (min 0). 0 = correctie → daarna
                        verwijderbaar. */}
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">
                        {r.type === "refund" ? "Terugbetaald bedrag (€)" : "Betaald bedrag (€)"}
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        {...(r.type === "refund" ? { max: 0 } : { min: 0 })}
                        className="input text-sm"
                        placeholder={parseFloat(r.amount).toFixed(2)}
                        value={editData.amount_paid}
                        onChange={(e) => setEditData((d) => ({ ...d, amount_paid: e.target.value }))}
                      />
                      {r.type === "refund" && (
                        <p className="text-[11px] text-gray-400 mt-0.5">
                          Negatief bedrag; zet op 0 om te corrigeren (dan verwijderbaar).
                        </p>
                      )}
                    </div>
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Opmerking</label>
                      <input
                        type="text"
                        className="input text-sm"
                        placeholder="Opmerking…"
                        value={editData.note}
                        onChange={(e) => setEditData((d) => ({ ...d, note: e.target.value }))}
                      />
                    </div>
                  </div>
                  {editError && (
                    <p className="text-red-600 text-sm mb-2">{editError}</p>
                  )}
                  <div className="flex gap-2">
                    <button
                      onClick={() => saveEdit(r.id)}
                      disabled={saving}
                      className="btn-primary text-sm"
                    >
                      {saving ? "Opslaan…" : "Opslaan"}
                    </button>
                    <button
                      onClick={() => { setEditing(null); setEditError(null); }}
                      className="btn-secondary text-sm"
                    >
                      Annuleren
                    </button>
                  </div>
                </div>
              )}

              {refunding === r.id && (
                <div className="mt-3 pt-3 border-t border-orange-100 space-y-3">
                  <p className="text-sm font-medium text-orange-700">Terugbetaling registreren</p>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Bedrag (€)</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        className="input text-sm"
                        placeholder={r.amount_paid ? parseFloat(r.amount_paid).toFixed(2) : "0.00"}
                        value={refundData.amount}
                        onChange={(e) => setRefundData((d) => ({ ...d, amount: e.target.value }))}
                      />
                    </div>
                    <div className="sm:col-span-3">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Reden / opmerking</label>
                      <input
                        type="text"
                        className="input text-sm"
                        placeholder="bv. afgehaakt, helper-tarief…"
                        value={refundData.note}
                        onChange={(e) => setRefundData((d) => ({ ...d, note: e.target.value }))}
                      />
                    </div>
                  </div>
                  {refundError && (
                    <p className="text-red-600 text-sm mb-2">{refundError}</p>
                  )}
                  <div className="flex gap-2">
                    <button
                      onClick={() => saveRefund(r.id)}
                      disabled={refundSaving}
                      className="btn-primary text-sm"
                    >
                      {refundSaving ? "Bezig…" : "Terugbetaling opslaan"}
                    </button>
                    <button
                      onClick={() => { setRefunding(null); setRefundError(null); }}
                      className="btn-secondary text-sm"
                    >
                      Annuleren
                    </button>
                  </div>
                </div>
              )}
            </div>
              ))}
              {g.recs.length > 1 && (() => {
                const sumA = g.recs.reduce((s, r) => s + parseFloat(r.amount), 0);
                const sumP = g.recs.reduce((s, r) => s + (r.amount_paid ? parseFloat(r.amount_paid) : 0), 0);
                const sumS = sumA - sumP;
                return (
                  <div className="flex justify-end gap-4 px-2 pb-1 text-sm font-semibold text-gray-700 flex-wrap">
                    <span>Totaal inschrijving</span>
                    <span>Bedrag: €{sumA.toFixed(2)}</span>
                    <span className="text-green-700">Ontvangen: €{sumP.toFixed(2)}</span>
                    <span className={sumS > 0.001 ? "text-red-600" : "text-green-600"}>
                      Saldo: €{sumS.toFixed(2)}
                    </span>
                  </div>
                );
              })()}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
