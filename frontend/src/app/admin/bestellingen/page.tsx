"use client";
import { useEffect, useState } from "react";
import { getOrders, exportOrders, getProductTotals } from "@/lib/api";
import type { Order } from "@/lib/types";

interface ProductTotal { product: string; quantity: number; revenue: number; }

export default function AdminBestellingen() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [totals, setTotals] = useState<ProductTotal[]>([]);

  useEffect(() => {
    getOrders().then((r) => setOrders(r.data)).catch(() => {});
    getProductTotals().then((r) => setTotals(r.data)).catch(() => {});
  }, []);

  async function handleExport() {
    const res = await exportOrders();
    const url = URL.createObjectURL(new Blob([res.data]));
    const a = document.createElement("a");
    a.href = url;
    a.download = "bestellingen.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const statusClass: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    paid: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-blue-800">Bestellingen</h1>
        <button className="btn-secondary btn-sm" onClick={handleExport}>📥 Exporteer CSV</button>
      </div>

      {totals.length > 0 && (
        <div className="card mb-6">
          <h2 className="font-semibold mb-3">Totalen per product (betaald)</h2>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-gray-500 border-b"><th className="pb-2 pr-4">Product</th><th className="pb-2 pr-4">Aantal</th><th className="pb-2">Omzet</th></tr></thead>
            <tbody>
              {totals.map((t) => (
                <tr key={t.product} className="border-b">
                  <td className="py-2 pr-4">{t.product}</td>
                  <td className="py-2 pr-4 font-bold">{t.quantity}</td>
                  <td className="py-2">€{t.revenue.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="space-y-3">
        {orders.map((o) => (
          <div key={o.id} className="card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold">{o.confirmation_number}</div>
                <div className="text-sm text-gray-700">{o.customer_name} · {o.customer_email}</div>
                <div className="text-sm text-gray-500">
                  {new Date(o.created_at).toLocaleDateString("nl-BE")} · €{parseFloat(o.total_amount).toFixed(2)}
                  {o.is_member && " · Lid"}
                </div>
                <div className="mt-1 text-sm">
                  {o.items.map((item, i) => (
                    <span key={i}>{i > 0 ? ", " : ""}{item.quantity}× {item.product?.name || `product #${item.product_id}`}</span>
                  ))}
                </div>
              </div>
              <span className={`text-xs px-2 py-1 rounded-full ${statusClass[o.payment_status] || "bg-gray-100"}`}>
                {o.payment_status}
              </span>
            </div>
          </div>
        ))}
        {orders.length === 0 && <p className="text-gray-500 text-sm">Geen bestellingen.</p>}
      </div>
    </div>
  );
}
