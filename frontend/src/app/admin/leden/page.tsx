"use client";
import { useCallback, useEffect, useState } from "react";
import {
  getFamilies, getFamily, createMembership, deleteMembership, deleteFamily,
  addPersonToFamily, assignBoardMember, listPersons,
  updatePerson, updatePersonAddress, updatePersonContacts, deletePerson,
  getGenderCodes, getRelationTypes,
} from "@/lib/api";
import type { Family, FamilyMember, Membership } from "@/lib/types";
import { type PostalOption, type PersonInput, type AddressInput, emptyPerson, emptyAddress } from "@/components/household/types";
import PersonFields from "@/components/household/PersonFields";
import AddressFields from "@/components/household/AddressFields";

interface PersonItem { id: number; last_name: string; first_name: string; }

function isHoofdlid(m: FamilyMember) {
  return m.relation_type?.toUpperCase() === "HOOFDLID";
}

function relationLabel(code: string | null) {
  const map: Record<string, string> = { HOOFDLID: "Hoofdlid", PARTNER: "Partner", KIND: "Kind" };
  return code ? (map[code.toUpperCase()] ?? code) : "—";
}

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
  const [editForm, setEditForm] = useState<PersonInput>(emptyPerson());
  const [addressForm, setAddressForm] = useState<AddressInput>(emptyAddress());
  const [editingAddress, setEditingAddress] = useState(false);
  const [showAddPerson, setShowAddPerson] = useState(false);
  const [newPersonForm, setNewPersonForm] = useState<PersonInput>(emptyPerson("PARTNER"));

  // Zoek + paginatie (#233): de lijst is server-side gepagineerd, dus we zoeken
  // server-side zodat ook leden buiten de huidige pagina vindbaar zijn.
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const loadFamilies = useCallback(() => {
    return getFamilies({ page, q: q.trim() || undefined })
      .then((r) => { setFamilies(r.data.items); setTotalPages(r.data.total_pages || 1); })
      .catch(() => {});
  }, [page, q]);

  async function loadFamily(id: number) {
    const r = await getFamily(id);
    setSelected(r.data);
  }

  useEffect(() => {
    listPersons().then((r) => setAllPersons(r.data)).catch(() => {});
    getGenderCodes().then((r) => setGenderCodes(r.data)).catch(() => {});
    getRelationTypes().then((r) => setRelationTypes(r.data)).catch(() => {});
    fetch("/api/v1/postal-codes").then((r) => r.json()).then(setPostalCodes).catch(() => {});
  }, []);

  // Gezinnen (her)laden bij wijziging van pagina of zoekterm (zoek licht gedebounced).
  useEffect(() => {
    const t = setTimeout(loadFamilies, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [loadFamilies, q]);

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
    setEditForm({
      first_name: m.first_name,
      last_name: m.last_name,
      date_of_birth: m.date_of_birth || "",
      gender_code: m.gender || "",
      email: m.email || "",
      phone: m.phone || "",
      mobile: m.mobile || "",
      relation_type: m.relation_type || "",
    });
  }

  async function handleSavePerson() {
    if (!editingPerson) return;
    await updatePerson(editingPerson.id, {
      last_name: editForm.last_name,
      first_name: editForm.first_name,
      date_of_birth: editForm.date_of_birth || null,
      gender_code: editForm.gender_code || null,
    });
    await updatePersonContacts(editingPerson.id, {
      email: editForm.email || null,
      phone: editForm.phone || null,
      mobile: editForm.mobile || null,
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
    const primary = selected.members.find(isHoofdlid) ?? selected.members[0];
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
      first_name: newPersonForm.first_name,
      last_name: newPersonForm.last_name,
      date_of_birth: newPersonForm.date_of_birth || null,
      gender_code: newPersonForm.gender_code || null,
      email: newPersonForm.email || null,
      phone: newPersonForm.phone || null,
      mobile: newPersonForm.mobile || null,
      relation_type: newPersonForm.relation_type,
    });
    setShowAddPerson(false);
    setNewPersonForm(emptyPerson("PARTNER"));
    loadFamily(selected.id);
  }

  async function handleBoardMember(personId: string) {
    if (!selected) return;
    await assignBoardMember(selected.id, { person_id: personId ? parseInt(personId) : null });
    loadFamily(selected.id);
  }

  function memberRow(m: FamilyMember) {
    if (editingPerson?.id === m.id) {
      return (
        <div key={m.id} className="card">
          <PersonFields
            person={editForm}
            onChange={(patch) => setEditForm((f) => ({ ...f, ...patch }))}
            genderCodes={genderCodes}
          />
          <div className="flex gap-2 mt-3">
            <button className="btn-primary btn-sm" onClick={handleSavePerson}>Opslaan</button>
            <button className="btn-secondary btn-sm" onClick={() => setEditingPerson(null)}>Annuleren</button>
          </div>
        </div>
      );
    }
    // Card-stijl van "Mijn gezin", met de boxed knoppen van admin.
    return (
      <div key={m.id} className="card">
        <div className="flex items-start justify-between">
          <div>
            <span className="font-semibold text-gray-900">{m.first_name} {m.last_name}</span>
            <span className="text-xs text-gray-500 ml-1">({relationLabel(m.relation_type)})</span>
            {m.date_of_birth && (
              <p className="text-sm text-gray-500 mt-0.5">° {new Date(m.date_of_birth).toLocaleDateString("nl-BE")}</p>
            )}
            <div className="text-sm text-gray-500 mt-0.5">
              <div className="flex gap-3 flex-wrap">
                {m.email && <span>✉ {m.email}</span>}
                {m.mobile && <span>📱 {m.mobile}</span>}
              </div>
              {m.phone && <div>☎ {m.phone}</div>}
            </div>
          </div>
          <div className="flex gap-2 shrink-0 ml-4">
            <button className="btn-secondary btn-sm" onClick={() => startEditPerson(m)}>Bewerken</button>
            {!isHoofdlid(m) && (
              <button className="btn-danger btn-sm" onClick={() => handleDeletePerson(m)}>Verwijderen</button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const hoofdlid = selected?.members.find(isHoofdlid) ?? selected?.members[0];
  const overige = selected?.members.filter((m) => m.id !== hoofdlid?.id) ?? [];

  return (
    <div className="flex flex-col md:flex-row gap-6">
      {/* Gezinnenlijst */}
      <div className="md:w-64 shrink-0">
        <h1 className="text-2xl font-bold text-blue-800 mb-4">Leden</h1>
        <input
          type="search"
          placeholder="Zoek op naam of e-mail…"
          className="input text-sm mb-3 w-full"
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
        />
        <div className="space-y-2">
          {families.map((f) => {
            const primary = f.members.find(isHoofdlid) ?? f.members[0];
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
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-3 text-sm">
            <button
              className="px-2 py-1 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              ← Vorige
            </button>
            <span className="text-gray-500">pagina {page} van {totalPages}</span>
            <button
              className="px-2 py-1 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Volgende →
            </button>
          </div>
        )}
      </div>

      {/* Detail */}
      {selected && (
        <div className="flex-1 min-w-0 space-y-4">

          {/* Kop */}
          <div className="card">
            <div className="flex items-center justify-between">
              <h2 className="font-bold text-lg">Gezin #{selected.id}</h2>
              <button className="btn-danger btn-sm" onClick={() => handleDeleteFamily(selected.id)}>Verwijderen</button>
            </div>
          </div>

          {/* Gezinsleden — hoofdlid → adres → overige leden (cards zoals "Mijn gezin") */}
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-700">Gezinsleden</h3>
            <button className="btn-secondary btn-sm" onClick={() => setShowAddPerson((v) => !v)}>+ Persoon toevoegen</button>
          </div>

          {showAddPerson && (
            <div className="card bg-blue-50 space-y-3">
              <h4 className="font-medium text-sm">Nieuwe persoon</h4>
              <PersonFields
                person={newPersonForm}
                onChange={(patch) => setNewPersonForm((f) => ({ ...f, ...patch }))}
                genderCodes={genderCodes}
              />
              <div>
                <label className="label">Relatie</label>
                <select className="input" value={newPersonForm.relation_type} onChange={(e) => setNewPersonForm((f) => ({ ...f, relation_type: e.target.value }))}>
                  {relationTypes.filter((r) => r.code !== "HOOFDLID").map((r) => <option key={r.code} value={r.code}>{r.value}</option>)}
                </select>
              </div>
              <div className="flex gap-2">
                <button className="btn-primary btn-sm" onClick={handleAddPerson} disabled={!newPersonForm.last_name || !newPersonForm.first_name}>Toevoegen</button>
                <button className="btn-secondary btn-sm" onClick={() => { setShowAddPerson(false); setNewPersonForm(emptyPerson("PARTNER")); }}>Annuleren</button>
              </div>
            </div>
          )}

          {/* Hoofdlid */}
          {hoofdlid && memberRow(hoofdlid)}

          {/* Adres — hoort bij het hoofdlid, getoond ná het hoofdlid (#133) */}
          <div className="card">
            {editingAddress ? (
              <div className="space-y-3">
                <AddressFields address={addressForm} onChange={(patch) => setAddressForm((f) => ({ ...f, ...patch }))} postalCodes={postalCodes} />
                <div className="flex gap-2">
                  <button className="btn-primary btn-sm" onClick={handleSaveAddress}>Opslaan</button>
                  <button className="btn-secondary btn-sm" onClick={() => setEditingAddress(false)}>Annuleren</button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-gray-700">
                  📍 {selected.street} {selected.house_number}{selected.bus_number ? ` bus ${selected.bus_number}` : ""}, {selected.postal_code} {selected.municipality}
                </span>
                <button className="btn-secondary btn-sm shrink-0" onClick={startEditAddress}>Adres bewerken</button>
              </div>
            )}
          </div>

          {/* Overige gezinsleden */}
          {overige.map((m) => memberRow(m))}

          {/* Bestuurslid — tussen gezinsleden en lidmaatschappen (#133) */}
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
