"use client";
import { useState } from "react";
import { createFamily } from "@/lib/api";

interface MemberForm {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender: string;
  email: string;
  phone: string;
  is_primary: boolean;
}

const emptyMember = (): MemberForm => ({
  first_name: "", last_name: "", date_of_birth: "", gender: "", email: "", phone: "", is_primary: false,
});

export default function FamilyRegistrationForm() {
  const [form, setForm] = useState({
    street: "", house_number: "", bus_number: "", postal_code: "", municipality: "",
  });
  const [members, setMembers] = useState<MemberForm[]>([{ ...emptyMember(), is_primary: true }]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState("");

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

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Adresgegevens</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
          <div>
            <label className="label">Postcode *</label>
            <input className="input" required value={form.postal_code} onChange={(e) => setForm((f) => ({ ...f, postal_code: e.target.value }))} />
          </div>
          <div>
            <label className="label">Gemeente *</label>
            <input className="input" required value={form.municipality} onChange={(e) => setForm((f) => ({ ...f, municipality: e.target.value }))} />
          </div>
        </div>
      </div>

      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Gezinsleden</h3>
        <div className="space-y-4">
          {members.map((member, i) => (
            <div key={i} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="flex items-center justify-between mb-3">
                <span className="font-medium text-sm text-gray-700">
                  {member.is_primary ? "Hoofdgezinslid" : `Gezinslid ${i + 1}`}
                </span>
                {!member.is_primary && (
                  <button type="button" onClick={() => removeMember(i)} className="text-red-600 text-sm hover:underline">
                    Verwijderen
                  </button>
                )}
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
                    <option value="V">Vrouw</option>
                    <option value="X">Anders</option>
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
              </div>
            </div>
          ))}
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
