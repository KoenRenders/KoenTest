"use client";
import { useState, useEffect } from "react";
import { createFamily, getGenderCodes, getRelationTypes } from "@/lib/api";
import { trackEvent } from "@/lib/analytics";
import { type PersonInput, type AddressInput, emptyPerson, emptyAddress } from "./household/types";
import { usePostalCodes } from "./household/usePostalCodes";
import PersonFields from "./household/PersonFields";
import AddressFields from "./household/AddressFields";
import PaymentMethodChoice from "./household/PaymentMethodChoice";

export default function FamilyRegistrationForm() {
  const [members, setMembers] = useState<PersonInput[]>([emptyPerson("HOOFDLID")]);
  const [address, setAddress] = useState<AddressInput>(emptyAddress());
  const [paymentMethod, setPaymentMethod] = useState("online");
  const [genderCodes, setGenderCodes] = useState<{ code: string; value: string }[]>([]);
  const [relationTypes, setRelationTypes] = useState<{ code: string; value: string }[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState("");
  const postalCodes = usePostalCodes();

  useEffect(() => {
    getGenderCodes().then((r) => setGenderCodes(r.data)).catch(() => {});
    getRelationTypes().then((r) => setRelationTypes(r.data)).catch(() => {});
  }, []);

  function updateMember(i: number, patch: Partial<PersonInput>) {
    setMembers((ms) => ms.map((m, idx) => idx === i ? { ...m, ...patch } : m));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!address.postal_code) {
      setError("Selecteer een geldige postcode uit de lijst.");
      setStatus("error");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const res = await createFamily({
        street: address.street,
        house_number: address.house_number,
        bus_number: address.bus_number || undefined,
        postal_code: address.postal_code,
        payment_method: paymentMethod,
        members: members.map((m) => ({
          first_name: m.first_name,
          last_name: m.last_name,
          date_of_birth: m.date_of_birth || undefined,
          gender_code: m.gender_code || undefined,
          email: m.email || undefined,
          phone: m.phone || undefined,
          mobile: m.mobile || undefined,
          relation_type: m.relation_type,
        })),
      });
      const data = res.data;
      // Funnel-event (#152, laag 1) — geen PII, enkel de betaalkeuze.
      trackEvent("lid-worden-verzonden", { betaalkeuze: paymentMethod });
      if (paymentMethod === "online" && data.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        setStatus("success");
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || "Er is iets misgelopen. Controleer je gegevens en probeer opnieuw.");
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-green-800">
        <h3 className="font-bold text-lg mb-2">Registratie ontvangen!</h3>
        <p>Je gezin is geregistreerd. Je ontvangt een bevestiging per e-mail zodra de betaling verwerkt is.</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Hoofdgezinslid */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Hoofdgezinslid</h3>
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
          <PersonFields
            person={members[0]}
            onChange={(patch) => updateMember(0, patch)}
            genderCodes={genderCodes}
            requireContact
          />
        </div>
      </div>

      {/* Adresgegevens — enkel het hoofdlid (= gezinsadres) */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Adresgegevens</h3>
        <AddressFields address={address} onChange={(patch) => setAddress((a) => ({ ...a, ...patch }))} postalCodes={postalCodes} />
      </div>

      {/* Extra gezinsleden */}
      {members.length > 1 && (
        <div>
          <h3 className="font-semibold text-lg mb-3 text-blue-800">Overige gezinsleden</h3>
          <div className="space-y-4">
            {members.slice(1).map((member, i) => (
              <div key={i + 1} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                <div className="flex items-center gap-3 justify-between mb-3">
                  <select
                    className="input flex-1 max-w-xs font-medium text-sm"
                    value={member.relation_type}
                    onChange={(e) => updateMember(i + 1, { relation_type: e.target.value })}
                  >
                    {relationTypes.filter((t) => t.code !== "HOOFDLID").map((t) => (
                      <option key={t.code} value={t.code}>{t.value}</option>
                    ))}
                  </select>
                  <button type="button" onClick={() => setMembers((ms) => ms.filter((_, idx) => idx !== i + 1))} className="text-red-600 text-sm hover:underline whitespace-nowrap">
                    Verwijderen
                  </button>
                </div>
                <PersonFields
                  person={member}
                  onChange={(patch) => updateMember(i + 1, patch)}
                  genderCodes={genderCodes}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      <button type="button" onClick={() => setMembers((ms) => [...ms, emptyPerson("PARTNER")])} className="btn-secondary btn-sm">
        + Gezinslid toevoegen
      </button>

      {/* Betaling */}
      <PaymentMethodChoice value={paymentMethod} onChange={setPaymentMethod} />

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <button type="submit" disabled={status === "loading"} className="btn-primary">
        {status === "loading" ? "Bezig…" : paymentMethod === "online" ? "Registreren en betalen" : "Gezin registreren"}
      </button>
    </form>
  );
}
