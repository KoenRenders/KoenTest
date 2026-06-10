"use client";
import { useEffect, useState } from "react";
import { listPaymentRecords, updatePaymentRecord } from "@/lib/api";

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
  const [filter, setFilter] = useState<"all" | "openstaand" | "pending" | "paid">("all");

  async function load() {
    try {
      const resp = await listPaymentRecords();
      setRecords(resp.data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function startEdit(r: PaymentRecord) {
    setEditing(r.id);
    setEditData({
      amount_paid: r.amount_paid ?? "",
      note: r.note ?? "",
      status: r.status,
    });
  }

  async function saveEdit(id: string) {
    setSaving(true);
    try {
      await updatePaymentRecord(id, {
        status: editData.status || undefined,
        amount_paid: editData.amount_paid ? parseFloat(editData.amount_paid) : undefined,
        note: editData.note || undefined,
      });
      setEditing(null);
      await load();
    } finally {
      setSaving(false);
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

      {/* Filter tabs */}
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

      {/* Totals */}
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
                  {r.items.length > 0 && (
                    <div className="mt-2 text-xs text-gray-600 border-t border-gray-100 pt-2 space-y-0.5">
                      {r.items.map((item, i) => (
                        <div key={i} className="flex justify-between gap-4">
                          <span>{item.quantity} × {item.product_name}</span>
                          <span className="tabular-nums">€{item.subtotal.toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {r.note && (
                    <p className="mt-1 text-sm text-gray-500 italic">{r.note}</p>
                  )}
                </div>
                {editing !== r.id && (
                  <button
                    onClick={() => startEdit(r)}
                    className="text-xs text-blue-600 border border-blue-200 rounded px-2 py-0.5 hover:bg-blue-50 whitespace-nowrap"
                  >
                    Bewerken
                  </button>
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
                  <div className="flex gap-2">
                    <button
                      onClick={() => saveEdit(r.id)}
                      disabled={saving}
                      className="btn-primary text-sm"
                    >
                      {saving ? "Opslaan…" : "Opslaan"}
                    </button>
                    <button
                      onClick={() => setEditing(null)}
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
