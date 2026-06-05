"use client";
import { useState, useEffect } from "react";
import { createFamily } from "@/lib/api";

interface PostalCodeOption {
  postal_code: string;
  municipality: string;
}

interface MemberForm {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender: string;
  email: string;
  phone: string;
  mobile: string;
  member_type: string;
  is_primary: boolean;
}

const emptyMember = (): MemberForm => ({
  first_name: "", last_name: "", date_of_birth: "", gender: "",
  email: "", phone: "", mobile: "", member_type: "", is_primary: false,
});

export default function FamilyRegistrationForm() {
  const [form, setForm] = useState({
    street: "", house_number: "", bus_number: "", postal_code: "", municipality: "",
  });
  const [members, setMembers] = useState<MemberForm[]>([{ ...emptyMember(), is_primary: true, member_type: "HOOFDLID" }]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState("");
  const [postalCodes, setPostalCodes] = useState<PostalCodeOption[]>([]);

  useEffect(() => {
    fetch("/api/v1/postal-codes")
      .then((r) => r.json())
      .then((data: PostalCodeOption[]) => setPostalCodes(data))
      .catch(() => {/* silently ignore, user can still type */});
  }, []);

  function handlePostalCodeChange(postalCode: string) {
    const match = postalCodes.find((p) => p.postal_code === postalCode);
    setForm((f) => ({ ...f, postal_code: postalCode, municipality: match ? match.municipality : "" }));
  }

  function updateMember(i: number, field: keyof MemberForm, value: string | boolean) {
    setMembers((ms) => ms.map((m, idx) => idx === i ? { ...m, [field]: value } : m));
  }

  function addMember() {
    setMembers((ms) => [...ms, emptyMember()]);
  }

  function removeMember(i: number) {
    if (members.length === 1) return;
    setMembers((ms) => ms.filter((_, idx) => idx !== i));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    setError("");
    try {
      await createFamily({
        ...form,
        bus_number: form.bus_number || undefined,
        members: members.map((m) => ({
          ...m,
          date_of_birth: m.date_of_birth || undefined,
          gender: m.gender || undefined,
          email: m.email || undefined,
          phone: m.phone || undefined,
          mobile: m.mobile || undefined,
        })),
      });
      setStatus("success");
    } catch {
      setError("Er is iets misgelopen. Controleer je gegevens en probeer opnieuw.");
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-green-800">
        <h3 className="font-bold text-lg mb-2">✅ Registratie ontvangen!</h3>
        <p>Je gezin is geregistreerd. Je ontvangt een bevestiging per e-mail.</p>
      </div>
    );
  }

  const memberTypeLabel = (m: MemberForm, i: number) => {
    if (m.is_primary) return "Hoofdlid";
    if (m.member_type === "PARTNER") return "Partner";
    if (m.member_type === "KIND") return "(Meerderjarig) kind";
    return `Gezinslid ${i + 1}`;
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Primary member fields */}
      {members.filter((m) => m.is_primary).map((member, _) => {
        const i = members.indexOf(member);
        return (
          <div key={i}>
            <h3 className="font-semibold text-lg mb-3 text-blue-800">Hoofdlid</h3>
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="label">Voornaam *</label>
                  <input className="input" required value={member.first_name} onChange={(e) => updateMember(i, "first_name", e.target.value)} />
                </div>
                <div>
                  <label className="label">Achternaam *</label>
                  <input className="input" required value={member.last_name} onChange={(e) => updateMember(i, "last_name", e.target.value)} />
                </div>
                <div>
                  <label className="label">Geboortedatum</label>
                  <input type="date" className="input" value={member.date_of_birth} onChange={(e) => updateMember(i, "date_of_birth", e.target.value)} />
                </div>
                <div>
                  <label className="label">Geslacht</label>
                  <select className="input" value={member.gender} onChange={(e) => updateMember(i, "gender", e.target.value)}>
                    <option value="">— Kies —</option>
                    <option value="M">Man</option>
                    <option value="F">Vrouw</option>
                    <option value="X">X</option>
                    <option value="U">Onbekend</option>
                  </select>
                </div>
                <div>
                  <label className="label">E-mailadres</label>
                  <input type="email" className="input" value={member.email} onChange={(e) => updateMember(i, "email", e.target.value)} />
                </div>
                <div>
                  <label className="label">Telefoonnummer</label>
                  <input type="tel" className="input" value={member.phone} onChange={(e) => updateMember(i, "phone", e.target.value)} />
                </div>
                <div>
                  <label className="label">Gsm-nummer</label>
                  <input type="tel" className="input" value={member.mobile} onChange={(e) => updateMember(i, "mobile", e.target.value)} />
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {/* Address section — under primary member */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Adresgegevens</h3>
        {/* Row 1: street + house number + bus */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-3">
          <div className="sm:col-span-2">
            <label className="label">Straat *</label>
            <input className="input" required value={form.street} onChange={(e) => setForm((f) => ({ ...f, street: e.target.value }))} />
          </div>
          <div>
            <label className="label">Nr. *</label>
            <input className="input" required value={form.house_number} onChange={(e) => setForm((f) => ({ ...f, house_number: e.target.value }))} />
          </div>
          <div>
            <label className="label">Bus</label>
            <input className="input" value={form.bus_number} onChange={(e) => setForm((f) => ({ ...f, bus_number: e.target.value }))} />
          </div>
        </div>
        {/* Row 2: postal code (dropdown) + municipality (read-only) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Postcode *</label>
            {postalCodes.length > 0 ? (
              <select
                className="input"
                required
                value={form.postal_code}
                onChange={(e) => handlePostalCodeChange(e.target.value)}
              >
                <option value="">— Kies postcode —</option>
                {postalCodes.map((p) => (
                  <option key={p.postal_code} value={p.postal_code}>
                    {p.postal_code}
                  </option>
                ))}
              </select>
            ) : (
              <input className="input" required value={form.postal_code} onChange={(e) => setForm((f) => ({ ...f, postal_code: e.target.value }))} />
            )}
          </div>
          <div>
            <label className="label">Gemeente</label>
            <input
              className="input bg-gray-100 cursor-not-allowed"
              readOnly
              value={form.municipality}
              placeholder="Automatisch ingevuld"
            />
          </div>
        </div>
      </div>

      {/* Additional family members */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Gezinsleden toevoegen</h3>
        <div className="space-y-4">
          {members.filter((m) => !m.is_primary).map((member) => {
            const i = members.indexOf(member);
            return (
              <div key={i} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-medium text-sm text-gray-700">{memberTypeLabel(member, i)}</span>
                  <button type="button" onClick={() => removeMember(i)} className="text-red-600 text-sm hover:underline">
                    Verwijderen
                  </button>
                </div>
                <div className="mb-3">
                  <label className="label">Type gezinslid</label>
                  <select className="input" value={member.member_type} onChange={(e) => updateMember(i, "member_type", e.target.value)}>
                    <option value="">— Kies —</option>
                    <option value="PARTNER">Partner</option>
                    <option value="KIND">(Meerderjarig) kind</option>
                  </select>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="label">Voornaam *</label>
                    <input className="input" required value={member.first_name} onChange={(e) => updateMember(i, "first_name", e.target.value)} />
                  </div>
                  <div>
                    <label className="label">Achternaam *</label>
                    <input className="input" required value={member.last_name} onChange={(e) => updateMember(i, "last_name", e.target.value)} />
                  </div>
                  <div>
                    <label className="label">Geboortedatum</label>
                    <input type="date" className="input" value={member.date_of_birth} onChange={(e) => updateMember(i, "date_of_birth", e.target.value)} />
                  </div>
                  <div>
                    <label className="label">Geslacht</label>
                    <select className="input" value={member.gender} onChange={(e) => updateMember(i, "gender", e.target.value)}>
                      <option value="">— Kies —</option>
                      <option value="M">Man</option>
                      <option value="F">Vrouw</option>
                      <option value="X">X</option>
                      <option value="U">Onbekend</option>
                    </select>
                  </div>
                  <div>
                    <label className="label">E-mailadres</label>
                    <input type="email" className="input" value={member.email} onChange={(e) => updateMember(i, "email", e.target.value)} />
                  </div>
                  <div>
                    <label className="label">Telefoonnummer</label>
                    <input type="tel" className="input" value={member.phone} onChange={(e) => updateMember(i, "phone", e.target.value)} />
                  </div>
                  <div>
                    <label className="label">Gsm-nummer</label>
                    <input type="tel" className="input" value={member.mobile} onChange={(e) => updateMember(i, "mobile", e.target.value)} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <button type="button" onClick={addMember} className="mt-3 btn-secondary btn-sm">
          + Gezinslid toevoegen
        </button>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <button type="submit" disabled={status === "loading"} className="btn-primary w-full sm:w-auto">
        {status === "loading" ? "Bezig…" : "Gezin registreren"}
      </button>
    </form>
  );
}
