"use client";
import type { PersonInput } from "./types";

// Gedeelde persoonsvelden. Geslacht komt altijd uit de DB-codes (#125).
// `requireContact` maakt e-mail + mobiel verplicht (voor het hoofdlid).
// Het relatietype wordt buiten dit component beheerd (per gezinslid-rij).
export default function PersonFields({
  person,
  onChange,
  genderCodes,
  requireContact = false,
}: {
  person: PersonInput;
  onChange: (patch: Partial<PersonInput>) => void;
  genderCodes: { code: string; value: string }[];
  requireContact?: boolean;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div>
        <label className="label">Voornaam *</label>
        <input className="input" required value={person.first_name} onChange={(e) => onChange({ first_name: e.target.value })} />
      </div>
      <div>
        <label className="label">Achternaam *</label>
        <input className="input" required value={person.last_name} onChange={(e) => onChange({ last_name: e.target.value })} />
      </div>
      <div>
        <label className="label">Geslacht</label>
        <select className="input" value={person.gender_code} onChange={(e) => onChange({ gender_code: e.target.value })}>
          <option value="">— Kies —</option>
          {genderCodes.map((g) => <option key={g.code} value={g.code}>{g.value}</option>)}
        </select>
      </div>
      <div>
        <label className="label">Geboortedatum</label>
        <input type="date" className="input" value={person.date_of_birth} onChange={(e) => onChange({ date_of_birth: e.target.value })} />
      </div>
      <div>
        <label className="label">E-mailadres{requireContact ? " *" : ""}</label>
        <input type="email" className="input" required={requireContact} value={person.email} onChange={(e) => onChange({ email: e.target.value })} />
      </div>
      <div>
        <label className="label">Mobiel nummer{requireContact ? " *" : ""}</label>
        <input type="tel" className="input" required={requireContact} value={person.mobile} onChange={(e) => onChange({ mobile: e.target.value })} />
      </div>
      <div>
        <label className="label">Telefoon</label>
        <input type="tel" className="input" value={person.phone} onChange={(e) => onChange({ phone: e.target.value })} />
      </div>
    </div>
  );
}
