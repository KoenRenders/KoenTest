"use client";
import { useState } from "react";
import { registerForActivity } from "@/lib/api";
import type { Activity, SubRegistration } from "@/lib/types";

interface Props {
  activity: Activity;
  subRegistration?: SubRegistration;
  onClose: () => void;
  onSuccess: () => void;
}

export default function RegistrationForm({ activity, subRegistration, onClose, onSuccess }: Props) {
  const formType = subRegistration?.reg_form_type ?? activity.reg_form_type ?? "INDIVIDUAL";

  // Parse age category config
  let ageCategories: { key: string; label: string }[] = [];
  if (formType === "AGE_CATEGORY" && activity.age_category_config) {
    try {
      ageCategories = JSON.parse(activity.age_category_config);
    } catch {
      ageCategories = [];
    }
  }

  // Parse paid products (sub_registrations where is_free=false and no reg_form_type)
  const paidProducts =
    formType === "PAID_PRODUCTS"
      ? (activity.sub_registrations ?? []).filter((s) => !s.is_free && !s.reg_form_type)
      : [];

  const isPaid =
    formType === "PAID_PER_PERSON" ||
    formType === "PAID_PRODUCTS" ||
    parseFloat(activity.price) > 0;

  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [teamName, setTeamName] = useState("");
  const [groupSize, setGroupSize] = useState(1);
  const [ageCounts, setAgeCounts] = useState<Record<string, number>>(
    Object.fromEntries(ageCategories.map((c) => [c.key, 0]))
  );
  const [itemQuantities, setItemQuantities] = useState<Record<number, number>>(
    Object.fromEntries(paidProducts.map((p) => [p.id, 0]))
  );
  const [remarks, setRemarks] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("MOLLIE");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const unitPrice = parseFloat(activity.price) || 0;

  // Compute total for display
  let displayTotal = 0;
  if (formType === "PAID_PER_PERSON") {
    displayTotal = groupSize * unitPrice;
  } else if (formType === "PAID_PRODUCTS") {
    for (const p of paidProducts) {
      displayTotal += (itemQuantities[p.id] || 0) * parseFloat(p.price);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const effectivePaymentMethod = isPaid ? paymentMethod : "FREE";

      const body: Record<string, unknown> = {
        contact_name: contactName,
        contact_email: contactEmail || undefined,
        contact_phone: contactPhone || undefined,
        remarks: remarks || undefined,
        payment_method: effectivePaymentMethod,
        sub_registration_id: subRegistration?.id ?? undefined,
      };

      if (formType === "TEAM") {
        body.team_name = teamName;
      }
      if (formType === "GROUP" || formType === "PAID_PER_PERSON") {
        body.group_size = groupSize;
      }
      if (formType === "AGE_CATEGORY") {
        body.age_categories = JSON.stringify(ageCounts);
      }
      if (formType === "PAID_PRODUCTS") {
        body.items = paidProducts
          .filter((p) => (itemQuantities[p.id] || 0) > 0)
          .map((p) => ({ sub_registration_id: p.id, quantity: itemQuantities[p.id] }));
      }

      await registerForActivity(activity.id, body);
      onSuccess();
    } catch {
      setError("Er is iets misgelopen. Probeer opnieuw.");
    } finally {
      setLoading(false);
    }
  }

  const title = subRegistration ? `${activity.name} – ${subRegistration.name}` : activity.name;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 overflow-y-auto max-h-[90vh]">
        <h2 className="text-xl font-bold mb-1">Inschrijven</h2>
        <p className="text-gray-600 mb-6">
          {title} – {new Date(activity.date).toLocaleDateString("nl-BE")}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Contact */}
          <div>
            <label className="label">Naam *</label>
            <input
              className="input"
              required
              value={contactName}
              onChange={(e) => setContactName(e.target.value)}
            />
          </div>
          <div>
            <label className="label">E-mail</label>
            <input
              type="email"
              className="input"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="label">GSM-nummer</label>
            <input
              type="tel"
              className="input"
              value={contactPhone}
              onChange={(e) => setContactPhone(e.target.value)}
            />
          </div>

          {/* Form-type specific */}
          {formType === "TEAM" && (
            <div>
              <label className="label">Ploegnaam *</label>
              <input
                className="input"
                required
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
              />
            </div>
          )}

          {(formType === "GROUP") && (
            <div>
              <label className="label">Aantal personen *</label>
              <input
                type="number"
                min={1}
                className="input"
                required
                value={groupSize}
                onChange={(e) => setGroupSize(parseInt(e.target.value) || 1)}
              />
            </div>
          )}

          {formType === "PAID_PER_PERSON" && (
            <div>
              <label className="label">Aantal personen *</label>
              <input
                type="number"
                min={1}
                className="input"
                required
                value={groupSize}
                onChange={(e) => setGroupSize(parseInt(e.target.value) || 1)}
              />
              {unitPrice > 0 && (
                <p className="text-sm text-gray-600 mt-1">
                  Totaal: {groupSize} × €{unitPrice.toFixed(2)} = <strong>€{displayTotal.toFixed(2)}</strong>
                </p>
              )}
            </div>
          )}

          {formType === "AGE_CATEGORY" && ageCategories.map((cat) => (
            <div key={cat.key}>
              <label className="label">{cat.label}</label>
              <input
                type="number"
                min={0}
                className="input"
                value={ageCounts[cat.key] ?? 0}
                onChange={(e) =>
                  setAgeCounts((prev) => ({ ...prev, [cat.key]: parseInt(e.target.value) || 0 }))
                }
              />
            </div>
          ))}

          {formType === "PAID_PRODUCTS" && paidProducts.length > 0 && (
            <div className="space-y-2">
              <p className="label">Producten</p>
              {paidProducts.map((p) => (
                <div key={p.id} className="flex items-center gap-3">
                  <span className="flex-1 text-sm text-gray-700">
                    {p.name} (€{parseFloat(p.price).toFixed(2)})
                  </span>
                  <input
                    type="number"
                    min={0}
                    className="input w-20"
                    value={itemQuantities[p.id] ?? 0}
                    onChange={(e) =>
                      setItemQuantities((prev) => ({ ...prev, [p.id]: parseInt(e.target.value) || 0 }))
                    }
                  />
                </div>
              ))}
              {displayTotal > 0 && (
                <p className="text-sm text-gray-600 font-medium">
                  Totaal: <strong>€{displayTotal.toFixed(2)}</strong>
                </p>
              )}
            </div>
          )}

          {/* Opmerkingen */}
          <div>
            <label className="label">Opmerkingen</label>
            <textarea
              className="input"
              rows={3}
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
            />
          </div>

          {/* Betaling */}
          {isPaid && (
            <div>
              <label className="label">Betaalmethode *</label>
              <select
                className="input"
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
              >
                <option value="MOLLIE">Mollie (online)</option>
                <option value="CASH">Cash</option>
                <option value="TRANSFER">Overschrijving</option>
              </select>
            </div>
          )}

          {error && <p className="text-red-600 text-sm">{error}</p>}

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
