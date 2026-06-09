"use client";
import { useState } from "react";
import { registerForActivity } from "@/lib/api";
import type { Activity, ActivityProduct } from "@/lib/types";

interface Props {
  activity: Activity;
  onClose: () => void;
  onSuccess: () => void;
}

function formatPrice(price: string, memberPrice?: string) {
  const p = parseFloat(price);
  if (p === 0) return "gratis";
  let label = `€${p.toFixed(2)}`;
  if (memberPrice && parseFloat(memberPrice) > 0) {
    label += ` / leden €${parseFloat(memberPrice).toFixed(2)}`;
  }
  return label;
}

export default function RegistrationForm({ activity, onClose, onSuccess }: Props) {
  const [contactName, setContactName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [teamName, setTeamName] = useState("");
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const components = activity.sub_registrations ?? [];
  const needsTeamName = components.some((c) => c.team_name_required);

  const allProducts: Array<{ product: ActivityProduct; componentName: string }> = [];
  for (const comp of components) {
    for (const p of comp.products) {
      allProducts.push({ product: p, componentName: comp.name });
    }
  }

  const totalAmount = allProducts.reduce((sum, { product }) => {
    const qty = quantities[product.id] ?? 0;
    if (qty === 0 || product.is_free) return sum;
    return sum + parseFloat(product.price) * qty;
  }, 0);

  const hasPaidItems = totalAmount > 0;
  const hasSelection = allProducts.some(({ product }) => (quantities[product.id] ?? 0) > 0);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!hasSelection) {
      setError("Selecteer minstens één product.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const items = allProducts
        .filter(({ product }) => (quantities[product.id] ?? 0) > 0)
        .map(({ product }) => ({ product_id: product.id, quantity: quantities[product.id] }));

      await registerForActivity(activity.id, {
        contact_name: contactName,
        contact_email: email || undefined,
        phone: phone || undefined,
        team_name: teamName || undefined,
        items,
      });
      onSuccess();
    } catch {
      setError("Er is iets misgelopen. Probeer opnieuw.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-xl font-bold mb-1">Inschrijven</h2>
        <p className="text-gray-600 mb-6">{activity.name} – {new Date(activity.date).toLocaleDateString("nl-BE")}</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Naam *</label>
            <input className="input" required value={contactName} onChange={(e) => setContactName(e.target.value)} />
          </div>
          <div>
            <label className="label">E-mailadres</label>
            <input type="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label">Telefoonnummer</label>
            <input type="tel" className="input" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>

          {needsTeamName && (
            <div>
              <label className="label">Ploegnaam *</label>
              <input className="input" required value={teamName} onChange={(e) => setTeamName(e.target.value)} />
            </div>
          )}

          {components.map((comp) => (
            <div key={comp.id}>
              <h3 className="font-semibold text-gray-800 mb-2 border-b pb-1">{comp.name}</h3>
              {comp.products.length === 0 && (
                <p className="text-sm text-gray-400 italic">Geen producten.</p>
              )}
              <div className="space-y-2">
                {comp.products.map((p) => (
                  <div key={p.id} className="flex items-center justify-between gap-3">
                    <div className="flex-1 text-sm">
                      <span className="font-medium">{p.name}</span>
                      <span className="ml-2 text-gray-500">{formatPrice(p.price, p.member_price)}</span>
                    </div>
                    <input
                      type="number"
                      min={0}
                      max={p.max_participants ?? 99}
                      className="input w-20 text-center"
                      value={quantities[p.id] ?? 0}
                      onChange={(e) => setQuantities((q) => ({ ...q, [p.id]: parseInt(e.target.value) || 0 }))}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}

          {hasPaidItems && (
            <div className="bg-blue-50 rounded-lg p-3 text-sm font-medium text-blue-800">
              Totaal: €{totalAmount.toFixed(2)}
              <p className="text-xs font-normal text-blue-600 mt-1">Betaling via overschrijving of cash op het evenement.</p>
            </div>
          )}

          {error && <p className="text-red-600 text-sm">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? "Bezig…" : "Inschrijven"}
            </button>
            <button type="button" className="btn-secondary" onClick={onClose}>Annuleren</button>
          </div>
        </form>
      </div>
    </div>
  );
}
