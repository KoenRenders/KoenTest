"use client";
import { useState } from "react";
import { registerForActivity } from "@/lib/api";
import type { Activity, SubRegistration } from "@/lib/types";
import { parseApiError } from "@/lib/errors";
import { formatPrice } from "@/lib/money";

interface Props {
  activity: Activity;
  subRegistration?: SubRegistration;
  onClose: () => void;
  onSuccess: () => void;
}

function isPositive(val?: string | null): boolean {
  return !!val && parseFloat(val) > 0;
}

export default function RegistrationForm({ activity, onClose, onSuccess }: Props) {
  const products = (activity.sub_registrations ?? []).filter((s) => !s.external_register_url);

  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [teamName, setTeamName] = useState("");
  const [quantities, setQuantities] = useState<Record<number, number>>(
    Object.fromEntries(products.map((p) => [p.id, 0]))
  );
  const [remarks, setRemarks] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("MOLLIE");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function computeTotal(): number {
    return products.reduce((sum, p) => {
      if (p.is_free) return sum;
      return sum + (quantities[p.id] || 0) * (parseFloat(p.price) || 0);
    }, 0);
  }

  const total = computeTotal();
  const isPaid = total > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    const items = products
      .filter((p) => (quantities[p.id] || 0) > 0)
      .map((p) => ({ sub_registration_id: p.id, quantity: quantities[p.id] }));

    try {
      const res = await registerForActivity(activity.id, {
        contact_name: contactName,
        contact_email: contactEmail,
        contact_phone: contactPhone,
        team_name: activity.team_name_required ? teamName : undefined,
        remarks: remarks || undefined,
        payment_method: isPaid ? paymentMethod : "FREE",
        items,
      });
      if (res.data?.checkout_url) {
        window.location.href = res.data.checkout_url;
      } else {
        onSuccess();
      }
    } catch (err) {
      setError(parseApiError(err, "Er is iets misgelopen. Probeer opnieuw."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 overflow-y-auto max-h-[90vh]">
        <h2 className="text-xl font-bold mb-1">Inschrijven</h2>
        <p className="text-gray-600 mb-6">
          {activity.name} – {new Date(activity.date).toLocaleDateString("nl-BE")}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Naam *</label>
            <input className="input" required value={contactName} onChange={(e) => setContactName(e.target.value)} />
          </div>
          <div>
            <label className="label">E-mail *</label>
            <input type="email" className="input" required value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} />
          </div>
          <div>
            <label className="label">GSM-nummer *</label>
            <input type="tel" className="input" required value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} />
          </div>

          {activity.team_name_required && (
            <div>
              <label className="label">Ploegnaam *</label>
              <input className="input" required value={teamName} onChange={(e) => setTeamName(e.target.value)} />
            </div>
          )}

          {products.length > 0 && (
            <div className="space-y-2">
              <p className="label">Inschrijving</p>
              {products.map((p) => (
                <div key={p.id} className="flex items-center gap-3">
                  <div className="flex-1 text-sm text-gray-700">
                    <span>{p.name}</span>
                    {p.is_free
                      ? <span className="ml-1 text-green-700">(gratis)</span>
                      : <span className="ml-1 text-gray-500">
                          ({formatPrice(p.price)}
                          {isPositive(p.member_price) ? ` / leden ${formatPrice(p.member_price!)}` : ""})
                        </span>
                    }
                  </div>
                  <input
                    type="number" min={0} className="input w-20"
                    value={quantities[p.id] ?? 0}
                    onChange={(e) => setQuantities((prev) => ({ ...prev, [p.id]: parseInt(e.target.value) || 0 }))}
                  />
                </div>
              ))}
            </div>
          )}

          <div>
            <label className="label">Opmerkingen</label>
            <textarea className="input" rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
          </div>

          {isPaid && (
            <div className="space-y-3">
              <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 flex justify-between items-center">
                <span className="font-medium text-blue-800">Totaal te betalen</span>
                <span className="font-bold text-blue-900 text-lg">{formatPrice(String(total.toFixed(2)))}</span>
              </div>
              <div>
                <label className="label">Betaalmethode *</label>
                <select className="input" value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}>
                  <option value="MOLLIE">Online (Mollie)</option>
                  <option value="CASH">Cash</option>
                  <option value="TRANSFER">Overschrijving</option>
                </select>
              </div>
            </div>
          )}

          {error && (
            <div className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-3 whitespace-pre-line">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button type="submit" disabled={loading} className="btn-primary flex-1">
              {loading ? "Bezig…" : "Inschrijven"}
            </button>
            <button type="button" onClick={onClose} className="btn-secondary flex-1">
              Annuleren
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
