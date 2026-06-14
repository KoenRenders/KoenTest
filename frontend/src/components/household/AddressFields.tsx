"use client";
import type { AddressInput, PostalOption } from "./types";
import PostalAutocomplete from "./PostalAutocomplete";

// Vaste adres-lay-out (Fixed UI-decision): 4-koloms grid. Rij 1: Straat (col-span-2)
// + Huisnummer + Bus. Rij 2: Postcode (volle breedte). Adres hoort enkel bij het
// hoofdlid (#125).
export default function AddressFields({
  address,
  onChange,
  postalCodes,
}: {
  address: AddressInput;
  onChange: (patch: Partial<AddressInput>) => void;
  postalCodes: PostalOption[];
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
      <div className="sm:col-span-2">
        <label className="label">Straat *</label>
        <input className="input" required value={address.street} onChange={(e) => onChange({ street: e.target.value })} />
      </div>
      <div>
        <label className="label">Nr. *</label>
        <input className="input" required value={address.house_number} onChange={(e) => onChange({ house_number: e.target.value })} />
      </div>
      <div>
        <label className="label">Bus</label>
        <input className="input" value={address.bus_number} onChange={(e) => onChange({ bus_number: e.target.value })} />
      </div>
      <div className="sm:col-span-4">
        <label className="label">Postcode *</label>
        <PostalAutocomplete
          value={address.postal_code}
          postalCodes={postalCodes}
          onChange={(code) => onChange({ postal_code: code })}
          required
        />
      </div>
    </div>
  );
}
