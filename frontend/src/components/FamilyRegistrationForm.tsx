"use client";
import { useState, useEffect } from "react";
import { parseApiError } from "@/lib/errors";

const RELATION_TYPES = ["hoofdlid", "partner", "kind", "meerderjarig kind"];

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
  relation_type: string;
}

const emptyMember = (): MemberForm => ({
  first_name: "", last_name: "", date_of_birth: "", gender: "",
  email: "", phone: "", mobile: "", relation_type: "partner",
});

function postalOption(p: PostalCodeOption) {
  return `${p.postal_code} — ${p.municipality}`;
}

function MemberFields({
  member, index, onChange,
}: {
  member: MemberForm;
  index: number;
  onChange: (field: keyof MemberForm, value: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div>
        <label className="label">Voornaam *</label>
        <input className="input" required value={member.first_name} onChange={(e) => onChange("first_name", e.target.value)} />
      </div>
      <div>
        <label className="label">Achternaam *</label>
        <input className="input" required value={member.last_name} onChange={(e) => onChange("last_name", e.target.value)} />
      </div>
      <div>
        <label className="label">Geboortedatum *</label>
        <input type="date" className="input" required value={member.date_of_birth} onChange={(e) => onChange("date_of_birth", e.target.value)} />
      </div>
      <div>
        <label className="label">Geslacht</label>
        <select className="input" value={member.gender} onChange={(e) => onChange("gender", e.target.value)}>
          <option value="">— Kies —</option>
          <option value="M">Man</option>
          <option value="F">Vrouw</option>
          <option value="X">X</option>
          <option value="U">Onbekend</option>
        </select>
      </div>
      <div>
        <label className="label">Telefoonnummer</label>
        <input type="tel" className="input" value={member.phone} onChange={(e) => onChange("phone", e.target.value)} />
      </div>
      <div>
        <label className="label">Gsm-nummer</label>
        <input type="tel" className="input" value={member.mobile} onChange={(e) => onChange("mobile", e.target.value)} />
      </div>
      <div className="sm:col-span-2">
        <label className="label">E-mailadres</label>
        <input type="email" className="input" value={member.email} onChange={(e) => onChange("email", e.target.value)} />
      </div>
    </div>
  );
}

export default function FamilyRegistrationForm() {
  const [form, setForm] = useState({
    street: "", house_number: "", bus_number: "", postal_code: "",
  });
  const [postalInput, setPostalInput] = useState("");
  const [members, setMembers] = useState<MemberForm[]>([{ ...emptyMember(), relation_type: "hoofdlid" }]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState("");
  const [postalCodes, setPostalCodes] = useState<PostalCodeOption[]>([]);

  useEffect(() => {
    fetch("/api/v1/postal-codes")
      .then((r) => r.json())
      .then((data: PostalCodeOption[]) => setPostalCodes(data))
      .catch(() => {});
  }, []);

  function handlePostalInput(value: string) {
    setPostalInput(value);
    const match = postalCodes.find((p) => postalOption(p) === value.trim() || p.postal_code === value.trim());
    setForm((f) => ({ ...f, postal_code: match ? match.postal_code : "" }));
  }

  function updateMember(i: number, field: keyof MemberForm, value: string) {
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
    if (!form.postal_code) {
      setError("Kies een geldige postcode uit de lijst.");
      setStatus("error");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const res = await fetch("/api/v1/families", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          street: form.street,
          house_number: form.house_number,
          bus_number: form.bus_number || undefined,
          postal_code: form.postal_code,
          members: members.map((m) => ({
            last_name: m.last_name,
            first_name: m.first_name,
            date_of_birth: m.date_of_birth,
            gender: m.gender || undefined,
            email: m.email || undefined,
            phone: m.phone || undefined,
            mobile: m.mobile || undefined,
            relation_type: m.relation_type,
          })),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail = body?.detail ?? "Onbekende fout";
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      setStatus("success");
    } catch (err) {
      setError(parseApiError(err));
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

  const hoofdlid = members.find((m) => m.relation_type === "hoofdlid")!;
  const hoofdlidIndex = members.indexOf(hoofdlid);
  const gezinsleden = members.filter((m) => m.relation_type !== "hoofdlid");

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Hoofdlid */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Hoofdlid</h3>
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
          <MemberFields member={hoofdlid} index={hoofdlidIndex} onChange={(f, v) => updateMember(hoofdlidIndex, f, v)} />
        </div>
      </div>

      {/* Adresgegevens */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Adresgegevens</h3>
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
        <div>
          <label className="label">Postcode / Gemeente *</label>
          <input
            className="input"
            list="postal-codes-list"
            required
            placeholder="Typ postcode of gemeente…"
            value={postalInput}
            onChange={(e) => handlePostalInput(e.target.value)}
          />
          <datalist id="postal-codes-list">
            {postalCodes.map((p) => (
              <option key={`${p.postal_code}-${p.municipality}`} value={postalOption(p)} />
            ))}
          </datalist>
          {postalInput && !form.postal_code && (
            <p className="text-red-500 text-xs mt-1">Kies een geldige postcode uit de lijst.</p>
          )}
        </div>
      </div>

      {/* Gezinsleden */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Gezinsleden toevoegen</h3>
        <div className="space-y-4">
          {gezinsleden.map((member) => {
            const i = members.indexOf(member);
            return (
              <div key={i} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-medium text-sm text-gray-700 capitalize">{member.relation_type}</span>
                  <button type="button" onClick={() => removeMember(i)} className="text-red-600 text-sm hover:underline">
                    Verwijderen
                  </button>
                </div>
                <div className="mb-3">
                  <label className="label">Relatie</label>
                  <select className="input" value={member.relation_type} onChange={(e) => updateMember(i, "relation_type", e.target.value)}>
                    {RELATION_TYPES.filter((r) => r !== "hoofdlid").map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </div>
                <MemberFields member={member} index={i} onChange={(f, v) => updateMember(i, f, v)} />
              </div>
            );
          })}
        </div>
        <button type="button" onClick={addMember} className="mt-3 btn-secondary btn-sm">
          + Gezinslid toevoegen
        </button>
      </div>

      {error && (
        <div className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-3 whitespace-pre-line">
          {error}
        </div>
      )}

      <button type="submit" disabled={status === "loading"} className="btn-primary w-full sm:w-auto">
        {status === "loading" ? "Bezig…" : "Gezin registreren"}
      </button>
    </form>
  );
}
