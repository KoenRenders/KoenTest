"use client";
import { useEffect, useState } from "react";
import { registerForActivity, getMemberMe } from "@/lib/api";
import type { Activity, ActivityComponent } from "@/lib/types";

interface Props {
  activity: Activity;
  component: ActivityComponent;
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

const PAYMENT_METHODS = [
  { value: "ONLINE", label: "Online betalen" },
  { value: "OVERSCHRIJVING", label: "Overschrijving" },
];

export default function RegistrationForm({ activity, component, onClose, onSuccess }: Props) {
  const [contactName, setContactName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [teamName, setTeamName] = useState("");
  const [remarks, setRemarks] = useState("");
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [paymentMethod, setPaymentMethod] = useState("ONLINE");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isMember, setIsMember] = useState(false);

  // Ingelogd lid? Velden voorinvullen en ledenprijs tonen. De backend blijft
  // de bron van waarheid voor het effectieve bedrag (op basis van person_id).
  useEffect(() => {
    if (typeof window === "undefined" || !localStorage.getItem("auth_token")) return;
    getMemberMe()
      .then((r) => {
        // Ledenprijs enkel tonen bij een geldig lidmaatschap op vandaag (#111).
        // De backend blijft de bron van waarheid voor het effectieve bedrag.
        setIsMember(r.data.has_valid_membership);
        setContactName((v) => v || r.data.name);
        setEmail((v) => v || r.data.email);
        setPhone((v) => v || r.data.phone || "");
      })
      .catch(() => {});
  }, []);

  const hasProducts = component.products.length > 0;

  function unitPrice(p: ActivityComponent["products"][number]) {
    if (isMember && p.member_price && parseFloat(p.member_price) >= 0) return parseFloat(p.member_price);
    return parseFloat(p.price);
  }

  const totalAmount = component.products.reduce((sum, p) => {
    const qty = quantities[p.id] ?? 0;
    if (qty === 0 || p.is_free) return sum;
    return sum + unitPrice(p) * qty;
  }, 0);

  const hasPaidItems = totalAmount > 0;
  const hasSelection = !hasProducts || component.products.some((p) => (quantities[p.id] ?? 0) > 0);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!hasSelection) {
      setError("Selecteer minstens één product.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const items = component.products
        .filter((p) => (quantities[p.id] ?? 0) > 0)
        .map((p) => ({ product_id: p.id, quantity: quantities[p.id] }));

      const resp = await registerForActivity(activity.id, {
        contact_name: contactName,
        contact_email: email,
        phone: phone || undefined,
        team_name: teamName || undefined,
        payment_method: hasPaidItems ? paymentMethod : undefined,
        component_id: component.id,
        items,
        remarks: remarks || undefined,
      });
      const checkout_url = resp.data?.checkout_url;
      if (checkout_url) {
        window.location.href = checkout_url;
      } else {
        onSuccess();
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ? `Fout: ${detail}` : "Er is iets misgelopen. Probeer opnieuw.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-xl font-bold mb-1">Inschrijven</h2>
        <p className="text-gray-500 text-sm mb-1">{activity.name} – {new Date(activity.date).toLocaleDateString("nl-BE")}</p>
        <p className="text-gray-800 font-semibold mb-5">{component.name}</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Naam *</label>
            <input className="input" required value={contactName} onChange={(e) => setContactName(e.target.value)} />
          </div>
          <div>
            <label className="label">E-mailadres *</label>
            <input type="email" className="input" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label">Mobiel nummer *</label>
            <input type="tel" className="input" required value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>

          {component.team_name_required && (
            <div>
              <label className="label">Ploegnaam *</label>
              <input className="input" required value={teamName} onChange={(e) => setTeamName(e.target.value)} />
            </div>
          )}

          {hasProducts && (
            <div>
              <h3 className="font-semibold text-gray-800 mb-2 border-b pb-1">{component.name}</h3>
              <div className="space-y-2">
                {component.products.map((p) => (
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
          )}

          {hasPaidItems && (
            <>
              <div className="bg-blue-50 rounded-lg p-3 text-sm font-medium text-blue-800">
                Totaal: €{totalAmount.toFixed(2)}
                {isMember && <span className="ml-2 font-normal text-blue-600">(ledenprijs)</span>}
              </div>
            </>
          )}

          <div>
            <label className="label">Opmerkingen</label>
            <textarea
              className="input"
              rows={3}
              placeholder="Eventuele boodschap voor de organisatie…"
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
            />
          </div>

          {hasPaidItems && (
            <div>
              <label className="label">Betaalwijze *</label>
              <div className="space-y-2">
                {PAYMENT_METHODS.map((m) => (
                  <label key={m.value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="paymentMethod"
                      value={m.value}
                      checked={paymentMethod === m.value}
                      onChange={() => setPaymentMethod(m.value)}
                    />
                    <span className="text-sm">{m.label}</span>
                  </label>
                ))}
              </div>
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
