"use client";
import { useEffect, useState } from "react";
import { listPaymentRecords, updatePaymentRecord, refreshPaymentRecord, getRegistrations } from "@/lib/api";
import { parseApiError } from "@/lib/errors";
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
  items: RegItem[];
  method: string;
  status: string;
  note: string | null;
  paid_at: string | null;
  created_at: string;
  description: string | null;
  contact_name: string | null;
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

  // Registration details: record id -> RegistrationEntry | null (null = loading)
  const [regDetails, setRegDetails] = useState<Record<string, RegistrationEntry | null>>({});

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

  function saldo(r: PaymentRecord) {
    return parseFloat(r.amount) - (r.amount_paid ? parseFloat(r.amount_paid) : 0);
  }

  const filtered = records.filter((r) => {
    if (filter === "pending") return r.status === "pending";
    if (filter === "paid") return r.status === "paid";
    if (filter === "openstaand") return saldo(r) > 0.001;
    return true;
  });

  const totalExpected = filtered.reduce((s, r) => s + parseFloat(r.amount), 0);
  const totalPaid = filtered.reduce((s, r) => s + (r.amount_paid ? parseFloat(r.amount_paid) : 0), 0);
  const totalSaldo = totalExpected - totalPaid;

  if (loading) return <p className="p-8 text-gray-500">Laden…</p>;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Betalingen</h1>

      <div className="flex gap-2 mb-6">
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
      </div>

      {error && (
        <p className="mb-4 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-3">{error}</p>
      )}

      <div className="flex gap-6 mb-6 text-sm text-gray-600 flex-wrap">
        <span>{filtered.length} betaling{filtered.length !== 1 ? "en" : ""}</span>
        <span>Verwacht: <strong>€{totalExpected.toFixed(2)}</strong></span>
        <span>Ontvangen: <strong>€{totalPaid.toFixed(2)}</strong></span>
        <span className={totalSaldo > 0.001 ? "text-red-600 font-semibold" : "text-green-600 font-semibold"}>
          Saldo: €{totalSaldo.toFixed(2)}
        </span>
      </div>

      {filtered.length === 0 ? (
        <p className="text-gray-500 italic">Geen betalingen gevonden.</p>
      ) : (
        <div className="space-y-3">
          {filtered.map((r) => (
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
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_COLORS[r.status] ?? "bg-gray-100 text-gray-600"}`}>
                      {STATUS_LABELS[r.status] ?? r.status}
                    </span>
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
                        </div>
                      )}
                    </div>
                  )}
                </div>
                {editing !== r.id && (
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
                        onChange={(e) => setEditData((d) => ({ ...d, status: e.target.value }))}
                      >
                        <option value="pending">In afwachting</option>
                        <option value="paid">Betaald</option>
                        <option value="failed">Mislukt</option>
                        <option value="cancelled">Geannuleerd</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Betaald bedrag (€)</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        className="input text-sm"
                        placeholder={parseFloat(r.amount).toFixed(2)}
                        value={editData.amount_paid}
                        onChange={(e) => setEditData((d) => ({ ...d, amount_paid: e.target.value }))}
                      />
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
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
