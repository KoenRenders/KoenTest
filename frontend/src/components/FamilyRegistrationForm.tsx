"use client";
import { useState, useEffect, useRef } from "react";
import { createFamily, getGenderCodes, getRelationTypes } from "@/lib/api";

interface PostalOption { postal_code: string; municipality: string; }
interface MemberForm {
  first_name: string; last_name: string; date_of_birth: string;
  gender: string; email: string; phone: string; mobile: string; relation_type: string;
}

const emptyMember = (relation_type = "HOOFDLID"): MemberForm => ({
  first_name: "", last_name: "", date_of_birth: "", gender: "",
  email: "", phone: "", mobile: "", relation_type,
});

export default function FamilyRegistrationForm() {
  const [form, setForm] = useState({
    street: "", house_number: "", bus_number: "", postal_code: "", payment_method: "online",
  });
  const [postalInput, setPostalInput] = useState("");
  const [postalOptions, setPostalOptions] = useState<PostalOption[]>([]);
  const [postalFiltered, setPostalFiltered] = useState<PostalOption[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [members, setMembers] = useState<MemberForm[]>([emptyMember("HOOFDLID")]);
  const [genderCodes, setGenderCodes] = useState<{ code: string; value: string }[]>([]);
  const [relationTypes, setRelationTypes] = useState<{ code: string; value: string }[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getGenderCodes().then((r) => setGenderCodes(r.data)).catch(() => {});
    getRelationTypes().then((r) => setRelationTypes(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    fetch("/api/v1/postal-codes")
      .then((r) => r.json())
      .then((data: PostalOption[]) => setPostalOptions(data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!postalInput) { setPostalFiltered([]); return; }
    const q = postalInput.toLowerCase();
    setPostalFiltered(
      postalOptions.filter(
        (p) => p.postal_code.startsWith(postalInput) || p.municipality.toLowerCase().includes(q)
      ).slice(0, 8)
    );
  }, [postalInput, postalOptions]);

  function selectPostal(p: PostalOption) {
    setPostalInput(`${p.postal_code} — ${p.municipality}`);
    setForm((f) => ({ ...f, postal_code: p.postal_code }));
    setShowDropdown(false);
  }

  function updateMember(i: number, field: keyof MemberForm, value: string) {
    setMembers((ms) => ms.map((m, idx) => idx === i ? { ...m, [field]: value } : m));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.postal_code) {
      setError("Selecteer een geldige postcode uit de lijst.");
      setStatus("error");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const res = await createFamily({
        street: form.street,
        house_number: form.house_number,
        bus_number: form.bus_number || undefined,
        postal_code: form.postal_code,
        payment_method: form.payment_method,
        members: members.map((m) => ({
          first_name: m.first_name,
          last_name: m.last_name,
          date_of_birth: m.date_of_birth || undefined,
          gender: m.gender || undefined,
          email: m.email || undefined,
          phone: m.phone || undefined,
          mobile: m.mobile || undefined,
          relation_type: m.relation_type,
        })),
      });
      const data = res.data;
      if (form.payment_method === "online" && data.checkout_url) {
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

  const memberFields = (i: number, member: MemberForm) => (
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
        <label className="label">Geslacht</label>
        <select className="input" value={member.gender} onChange={(e) => updateMember(i, "gender", e.target.value)}>
          <option value="">— Kies —</option>
          {genderCodes.map((g) => <option key={g.code} value={g.code}>{g.value}</option>)}
        </select>
      </div>
      <div>
        <label className="label">Geboortedatum</label>
        <input type="date" className="input" value={member.date_of_birth} onChange={(e) => updateMember(i, "date_of_birth", e.target.value)} />
      </div>
      <div>
        <label className="label">E-mailadres</label>
        <input type="email" className="input" value={member.email} onChange={(e) => updateMember(i, "email", e.target.value)} />
      </div>
      <div>
        <label className="label">Mobiel nummer</label>
        <input type="tel" className="input" value={member.mobile} onChange={(e) => updateMember(i, "mobile", e.target.value)} />
      </div>
      <div>
        <label className="label">Telefoon</label>
        <input type="tel" className="input" value={member.phone} onChange={(e) => updateMember(i, "phone", e.target.value)} />
      </div>
    </div>
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-6">

      {/* Hoofdgezinslid */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Hoofdgezinslid</h3>
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
          {memberFields(0, members[0])}
        </div>
      </div>

      {/* Adresgegevens */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Adresgegevens</h3>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
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
          <div className="sm:col-span-4 relative" ref={dropdownRef}>
            <label className="label">Postcode *</label>
            <input
              className="input"
              required
              autoComplete="off"
              value={postalInput}
              onChange={(e) => { setPostalInput(e.target.value); setForm((f) => ({ ...f, postal_code: "" })); setShowDropdown(true); }}
              onFocus={() => setShowDropdown(true)}
              onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
              placeholder="Type postcode of gemeente…"
            />
            {showDropdown && postalFiltered.length > 0 && (
              <ul className="absolute z-10 w-full bg-white border border-gray-200 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto">
                {postalFiltered.map((p) => (
                  <li key={p.postal_code}
                    className="px-3 py-2 hover:bg-blue-50 cursor-pointer text-sm"
                    onMouseDown={() => selectPostal(p)}>
                    <span className="font-medium">{p.postal_code}</span> — {p.municipality}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
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
                    onChange={(e) => updateMember(i + 1, "relation_type", e.target.value)}
                  >
                    {relationTypes.filter((t) => t.code !== "HOOFDLID").map((t) => (
                      <option key={t.code} value={t.code}>{t.value}</option>
                    ))}
                  </select>
                  <button type="button" onClick={() => setMembers((ms) => ms.filter((_, idx) => idx !== i + 1))} className="text-red-600 text-sm hover:underline whitespace-nowrap">
                    Verwijderen
                  </button>
                </div>
                {memberFields(i + 1, member)}
              </div>
            ))}
          </div>
        </div>
      )}

      <button type="button" onClick={() => setMembers((ms) => [...ms, emptyMember("PARTNER")])} className="btn-secondary btn-sm">
        + Gezinslid toevoegen
      </button>

      {/* Betaling */}
      <div>
        <h3 className="font-semibold text-lg mb-3 text-blue-800">Betaling</h3>
        <div className="space-y-2">
          {[
            { value: "online", label: "Online betalen" },
            { value: "transfer", label: "Overschrijving" },
          ].map(({ value, label }) => (
            <label key={value} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="payment_method" value={value}
                checked={form.payment_method === value}
                onChange={() => setForm((f) => ({ ...f, payment_method: value }))} />
              <span>{label}</span>
            </label>
          ))}
        </div>
        {form.payment_method === "online" && (
          <p className="mt-2 text-sm text-gray-600">Je wordt doorgestuurd naar Mollie om veilig online te betalen.</p>
        )}
        {form.payment_method === "transfer" && (
          <p className="mt-2 text-sm text-gray-600">Na registratie ontvang je de rekeninggegevens per e-mail.</p>
        )}
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <button type="submit" disabled={status === "loading"} className="btn-primary">
        {status === "loading" ? "Bezig…" : form.payment_method === "online" ? "Registreren en betalen" : "Gezin registreren"}
      </button>
    </form>
  );
}
