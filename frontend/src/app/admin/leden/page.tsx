"use client";
import { useEffect, useRef, useState } from "react";
import {
  getFamilies, getFamily, createMembership, deleteMembership, deleteFamily,
  addPersonToFamily, assignBoardMember, listPersons,
  updatePerson, updatePersonAddress, updatePersonContacts, deletePerson,
  getGenderCodes, getRelationTypes,
} from "@/lib/api";
import type { Family, FamilyMember, Membership } from "@/lib/types";

interface PersonItem { id: number; last_name: string; first_name: string; }
interface PostalOption { postal_code: string; municipality: string; }

function PostalAutocomplete({ value, onChange, postalCodes }: {
  value: string; onChange: (code: string) => void; postalCodes: PostalOption[];
}) {
  const [input, setInput] = useState(value);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const filtered = input.length < 2
    ? []
    : postalCodes.filter(
        (p) => p.postal_code.startsWith(input) || p.municipality.toLowerCase().includes(input.toLowerCase())
      ).slice(0, 8);

  useEffect(() => {
    function outside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, []);

  useEffect(() => { setInput(value); }, [value]);

  return (
    <div className="relative" ref={ref}>
      <input
        className="input"
        value={input}
        placeholder="Postcode of gemeente…"
        onChange={(e) => { setInput(e.target.value); onChange(""); setOpen(true); }}
        onFocus={() => setOpen(true)}
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-10 bg-white border border-gray-200 rounded shadow w-full mt-1 max-h-48 overflow-y-auto">
          {filtered.map((p) => (
            <li
              key={p.postal_code}
              className="px-3 py-2 hover:bg-blue-50 cursor-pointer text-sm"
              onMouseDown={() => { setInput(`${p.postal_code} — ${p.municipality}`); onChange(p.postal_code); setOpen(false); }}
            >
              <span className="font-medium">{p.postal_code}</span> — {p.municipality}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const emptyPersonForm = () => ({
  last_name: "", first_name: "", date_of_birth: "", gender_code: "",
  email: "", phone: "", mobile: "", relation_type: "PARTNER",
});

export default function AdminLeden() {
  const [families, setFamilies] = useState<Family[]>([]);
  const [selected, setSelected] = useState<Family | null>(null);
  const [allPersons, setAllPersons] = useState<PersonItem[]>([]);
  const [genderCodes, setGenderCodes] = useState<{ code: string; value: string }[]>([]);
  const [relationTypes, setRelationTypes] = useState<{ code: string; value: string }[]>([]);
  const [year, setYear] = useState(new Date().getFullYear());

  // edit states
  const [postalCodes, setPostalCodes] = useState<PostalOption[]>([]);
  const [editingPerson, setEditingPerson] = useState<FamilyMember | null>(null);
  const [personForm, setPersonForm] = useState({ last_name: "", first_name: "", date_of_birth: "", gender_code: "" });
  const [contactForm, setContactForm] = useState({ email: "", phone: "", mobile: "" });
  const [addressForm, setAddressForm] = useState({ street: "", house_number: "", bus_number: "", postal_code: "" });
  const [editingAddress, setEditingAddress] = useState(false);
  const [showAddPerson, setShowAddPerson] = useState(false);
  const [newPersonForm, setNewPersonForm] = useState(emptyPersonForm());

  function loadFamilies() {
    getFamilies().then((r) => setFamilies(r.data.items)).catch(() => {});
  }

  async function loadFamily(id: number) {
    const r = await getFamily(id);
    setSelected(r.data);
  }

  useEffect(() => {
    loadFamilies();
    listPersons().then((r) => setAllPersons(r.data)).catch(() => {});
    getGenderCodes().then((r) => setGenderCodes(r.data)).catch(() => {});
    getRelationTypes().then((r) => setRelationTypes(r.data)).catch(() => {});
    fetch("/api/v1/postal-codes").then((r) => r.json()).then(setPostalCodes).catch(() => {});
  }, []);

  async function handleDeleteFamily(id: number) {
    if (!confirm("Verwijder dit gezin en alle gezinsleden?")) return;
    await deleteFamily(id);
    setSelected(null);
    loadFamilies();
  }

  async function handleAddMembership() {
    if (!selected) return;
    await createMembership(selected.id, { year, is_active: true });
    loadFamily(selected.id);
  }

  async function handleDeleteMembership(ms: Membership) {
    if (!confirm(`Verwijder lidmaatschap ${ms.year}?`)) return;
    await deleteMembership(ms.id);
    loadFamily(selected!.id);
  }

  function startEditPerson(m: FamilyMember) {
    setEditingPerson(m);
    setPersonForm({ last_name: m.last_name, first_name: m.first_name, date_of_birth: m.date_of_birth || "", gender_code: m.gender || "" });
    setContactForm({ email: m.email || "", phone: m.phone || "", mobile: m.mobile || "" });
  }

  async function handleSavePerson() {
    if (!editingPerson) return;
    await updatePerson(editingPerson.id, {
      last_name: personForm.last_name,
      first_name: personForm.first_name,
      date_of_birth: personForm.date_of_birth || null,
      gender_code: personForm.gender_code || null,
    });
    await updatePersonContacts(editingPerson.id, {
      email: contactForm.email || null,
      phone: contactForm.phone || null,
      mobile: contactForm.mobile || null,
    });
    setEditingPerson(null);
    loadFamily(selected!.id);
  }

  function startEditAddress() {
    if (!selected) return;
    setAddressForm({
      street: selected.street,
      house_number: selected.house_number,
      bus_number: selected.bus_number || "",
      postal_code: selected.postal_code,
    });
    setEditingAddress(true);
  }

  async function handleSaveAddress() {
    if (!selected) return;
    const primary = selected.members.find((m) => m.relation_type?.toUpperCase() === "HOOFDLID") ?? selected.members[0];
    if (!primary) return;
    await updatePersonAddress(primary.id, {
      street: addressForm.street,
      house_number: addressForm.house_number,
      bus_number: addressForm.bus_number || null,
      postal_code: addressForm.postal_code,
    });
    setEditingAddress(false);
    loadFamily(selected.id);
  }

  async function handleDeletePerson(person: FamilyMember) {
    if (!confirm(`Verwijder ${person.first_name} ${person.last_name} uit dit gezin?`)) return;
    await deletePerson(person.id);
    loadFamily(selected!.id);
  }

  async function handleAddPerson() {
    if (!selected) return;
    await addPersonToFamily(selected.id, {
      ...newPersonForm,
      date_of_birth: newPersonForm.date_of_birth || null,
      gender_code: newPersonForm.gender_code || null,
      email: newPersonForm.email || null,
      phone: newPersonForm.phone || null,
      mobile: newPersonForm.mobile || null,
    });
    setShowAddPerson(false);
    setNewPersonForm(emptyPersonForm());
    loadFamily(selected.id);
  }

  async function handleBoardMember(personId: string) {
    if (!selected) return;
    await assignBoardMember(selected.id, { person_id: personId ? parseInt(personId) : null });
    loadFamily(selected.id);
  }

  return (
    <div className="flex flex-col md:flex-row gap-6">
      {/* Gezinnenlijst */}
      <div className="md:w-64 shrink-0">
        <h1 className="text-2xl font-bold text-blue-800 mb-4">Leden</h1>
        <div className="space-y-2">
          {families.map((f) => {
            const primary = f.members.find((m) => m.relation_type?.toUpperCase() === "HOOFDLID") ?? f.members[0];
            return (
              <button
                key={f.id}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm border transition-colors ${selected?.id === f.id ? "bg-blue-700 text-white border-blue-700" : "bg-white border-gray-200 hover:bg-gray-50"}`}
                onClick={() => { loadFamily(f.id); setEditingPerson(null); setEditingAddress(false); setShowAddPerson(false); }}
              >
                <div className="font-medium">{primary?.last_name || "—"} {primary?.first_name || ""}</div>
                <div className={`text-xs ${selected?.id === f.id ? "text-blue-200" : "text-gray-500"}`}>{f.street} {f.house_number}, {f.municipality}</div>
              </button>
            );
          })}
          {families.length === 0 && <p className="text-sm text-gray-500">Geen gezinnen gevonden.</p>}
        </div>
      </div>

      {/* Detail */}
      {selected && (
        <div className="flex-1 min-w-0 space-y-4">

          {/* Adres */}
          <div className="card">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-bold text-lg">Gezin #{selected.id}</h2>
              <div className="flex gap-2">
                <button className="btn-secondary btn-sm" onClick={startEditAddress}>Adres bewerken</button>
                <button className="btn-danger btn-sm" onClick={() => handleDeleteFamily(selected.id)}>Verwijderen</button>
              </div>
            </div>
            {editingAddress ? (
              <div className="space-y-3 mt-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2">
                    <label className="label">Straat</label>
                    <input className="input" value={addressForm.street} onChange={(e) => setAddressForm((f) => ({ ...f, street: e.target.value }))} />
                  </div>
                  <div>
                    <label className="label">Huisnummer</label>
                    <input className="input" value={addressForm.house_number} onChange={(e) => setAddressForm((f) => ({ ...f, house_number: e.target.value }))} />
                  </div>
                  <div>
                    <label className="label">Bus</label>
                    <input className="input" value={addressForm.bus_number} onChange={(e) => setAddressForm((f) => ({ ...f, bus_number: e.target.value }))} />
                  </div>
                  <div className="col-span-2">
                    <label className="label">Postcode</label>
                    <PostalAutocomplete
                      value={addressForm.postal_code}
                      postalCodes={postalCodes}
                      onChange={(code) => setAddressForm((f) => ({ ...f, postal_code: code }))}
                    />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="btn-primary btn-sm" onClick={handleSaveAddress}>Opslaan</button>
                  <button className="btn-secondary btn-sm" onClick={() => setEditingAddress(false)}>Annuleren</button>
                </div>
              </div>
            ) : (
              <p className="text-gray-700">{selected.street} {selected.house_number}{selected.bus_number ? ` bus ${selected.bus_number}` : ""}, {selected.postal_code} {selected.municipality}</p>
            )}
          </div>

          {/* Bestuurslid */}
          <div className="card">
            <h3 className="font-semibold mb-2">Verantwoordelijk bestuurslid</h3>
            <select
              className="input"
              value={selected.board_member?.id ?? ""}
              onChange={(e) => handleBoardMember(e.target.value)}
            >
              <option value="">— Geen —</option>
              {allPersons.map((p) => (
                <option key={p.id} value={p.id}>{p.last_name} {p.first_name}</option>
              ))}
            </select>
          </div>

          {/* Gezinsleden */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold">Gezinsleden</h3>
              <button className="btn-secondary btn-sm" onClick={() => setShowAddPerson((v) => !v)}>+ Persoon toevoegen</button>
            </div>

            {showAddPerson && (
              <div className="bg-blue-50 rounded-lg p-4 mb-4 space-y-3">
                <h4 className="font-medium text-sm">Nieuwe persoon</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="label">Achternaam *</label>
                    <input className="input" value={newPersonForm.last_name} onChange={(e) => setNewPersonForm((f) => ({ ...f, last_name: e.target.value }))} />
                  </div>
                  <div>
                    <label className="label">Voornaam *</label>
                    <input className="input" value={newPersonForm.first_name} onChange={(e) => setNewPersonForm((f) => ({ ...f, first_name: e.target.value }))} />
                  </div>
                  <div>
                    <label className="label">Geboortedatum</label>
                    <input type="date" className="input" value={newPersonForm.date_of_birth} onChange={(e) => setNewPersonForm((f) => ({ ...f, date_of_birth: e.target.value }))} />
                  </div>
                  <div>
                    <label className="label">Geslacht</label>
                    <select className="input" value={newPersonForm.gender_code} onChange={(e) => setNewPersonForm((f) => ({ ...f, gender_code: e.target.value }))}>
                      <option value="">—</option>
                      {genderCodes.map((g) => <option key={g.code} value={g.code}>{g.value}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="label">E-mail</label>
                    <input className="input" value={newPersonForm.email} onChange={(e) => setNewPersonForm((f) => ({ ...f, email: e.target.value }))} />
                  </div>
                  <div>
                    <label className="label">Telefoon</label>
                    <input className="input" value={newPersonForm.phone} onChange={(e) => setNewPersonForm((f) => ({ ...f, phone: e.target.value }))} />
                  </div>
                  <div>
                    <label className="label">GSM</label>
                    <input className="input" value={newPersonForm.mobile} onChange={(e) => setNewPersonForm((f) => ({ ...f, mobile: e.target.value }))} />
                  </div>
                  <div>
                    <label className="label">Relatie</label>
                    <select className="input" value={newPersonForm.relation_type} onChange={(e) => setNewPersonForm((f) => ({ ...f, relation_type: e.target.value }))}>
                      {relationTypes.map((r) => <option key={r.code} value={r.code}>{r.value}</option>)}
                    </select>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="btn-primary btn-sm" onClick={handleAddPerson} disabled={!newPersonForm.last_name || !newPersonForm.first_name}>Toevoegen</button>
                  <button className="btn-secondary btn-sm" onClick={() => { setShowAddPerson(false); setNewPersonForm(emptyPersonForm()); }}>Annuleren</button>
                </div>
              </div>
            )}

            <div className="space-y-3">
              {selected.members.map((m) => (
                <div key={m.id}>
                  {editingPerson?.id === m.id ? (
                    <div className="bg-gray-50 rounded-lg p-4 space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="label">Achternaam</label>
                          <input className="input" value={personForm.last_name} onChange={(e) => setPersonForm((f) => ({ ...f, last_name: e.target.value }))} />
                        </div>
                        <div>
                          <label className="label">Voornaam</label>
                          <input className="input" value={personForm.first_name} onChange={(e) => setPersonForm((f) => ({ ...f, first_name: e.target.value }))} />
                        </div>
                        <div>
                          <label className="label">Geboortedatum</label>
                          <input type="date" className="input" value={personForm.date_of_birth} onChange={(e) => setPersonForm((f) => ({ ...f, date_of_birth: e.target.value }))} />
                        </div>
                        <div>
                          <label className="label">Geslacht</label>
                          <select className="input" value={personForm.gender_code} onChange={(e) => setPersonForm((f) => ({ ...f, gender_code: e.target.value }))}>
                            <option value="">—</option>
                            {genderCodes.map((g) => <option key={g.code} value={g.code}>{g.value}</option>)}
                          </select>
                        </div>
                        <div>
                          <label className="label">E-mail</label>
                          <input className="input" value={contactForm.email} onChange={(e) => setContactForm((f) => ({ ...f, email: e.target.value }))} />
                        </div>
                        <div>
                          <label className="label">Telefoon</label>
                          <input className="input" value={contactForm.phone} onChange={(e) => setContactForm((f) => ({ ...f, phone: e.target.value }))} />
                        </div>
                        <div>
                          <label className="label">GSM</label>
                          <input className="input" value={contactForm.mobile} onChange={(e) => setContactForm((f) => ({ ...f, mobile: e.target.value }))} />
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button className="btn-primary btn-sm" onClick={handleSavePerson}>Opslaan</button>
                        <button className="btn-secondary btn-sm" onClick={() => setEditingPerson(null)}>Annuleren</button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between text-sm py-2 border-b border-gray-100 last:border-0">
                      <div>
                        <span className="font-medium">{m.first_name} {m.last_name}</span>
                        <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${m.relation_type?.toUpperCase() === "HOOFDLID" ? "bg-blue-100 text-blue-800" : "bg-gray-100 text-gray-600"}`}>{m.relation_type}</span>
                        <div className="text-gray-500 text-xs mt-0.5">
                          {m.date_of_birth && <span>{m.date_of_birth} · </span>}
                          {m.email && <span>{m.email} · </span>}
                          {m.phone && <span>{m.phone}{m.mobile ? " · " : ""}</span>}
                          {m.mobile && <span>{m.mobile}</span>}
                        </div>
                      </div>
                      <div className="flex gap-1 shrink-0 ml-2">
                        <button className="btn-secondary btn-sm" onClick={() => startEditPerson(m)}>Bewerken</button>
                        {m.relation_type?.toUpperCase() !== "HOOFDLID" && (
                          <button className="btn-danger btn-sm" onClick={() => handleDeletePerson(m)}>Verwijderen</button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Lidmaatschappen */}
          <div className="card">
            <h3 className="font-semibold mb-3">Lidmaatschappen</h3>
            {selected.memberships.length > 0 && (
              <div className="space-y-1 mb-4">
                {selected.memberships.map((ms) => (
                  <div key={ms.id} className="flex items-center justify-between text-sm py-1">
                    <span>{ms.year} {ms.is_active ? <span className="text-green-700 font-medium">· Actief</span> : <span className="text-gray-400">· Inactief</span>}</span>
                    <button className="btn-danger btn-sm" onClick={() => handleDeleteMembership(ms)}>Verwijderen</button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-3 items-end">
              <div>
                <label className="label">Jaar toevoegen</label>
                <input type="number" className="input w-28" value={year} onChange={(e) => setYear(parseInt(e.target.value))} />
              </div>
              <button className="btn-primary btn-sm" onClick={handleAddMembership}>Lid maken</button>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}
