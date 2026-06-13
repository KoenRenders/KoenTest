"use client";
import { useEffect, useState } from "react";
import { getAdminUsers, createAdminUser, updateAdminUser, deleteAdminUser, listPersons } from "@/lib/api";
import { parseApiError } from "@/lib/errors";

const ALL_ROLES = ["ADMIN", "MEMBER", "USER"];

interface PersonOption {
  id: number;
  first_name: string;
  last_name: string;
  street?: string;
  house_number?: string;
  postal_code?: string;
  municipality?: string;
}

interface UserEntry {
  id: number;
  email: string;
  is_active: boolean;
  person_id: number | null;
  person: { id: number; first_name: string; last_name: string } | null;
  roles: { role_code: string }[];
}

const emptyForm = () => ({
  email: "",
  is_active: true,
  person_id: null as number | null,
  role_codes: [] as string[],
});

function personLabel(p: PersonOption) {
  const addr = [p.street, p.house_number, p.postal_code, p.municipality].filter(Boolean).join(" ");
  return `${p.last_name} ${p.first_name}${addr ? ` — ${addr}` : ""}`;
}

export default function AdminGebruikers() {
  const [users, setUsers] = useState<UserEntry[]>([]);
  const [persons, setPersons] = useState<PersonOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState(emptyForm());
  const [personSearch, setPersonSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [ur, pr] = await Promise.all([getAdminUsers(), listPersons()]);
      setUsers(ur.data);
      setPersons(pr.data);
    } catch (e) {
      setError(parseApiError(e, "Kon gegevens niet laden."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function startCreate() {
    setEditId(null);
    setForm(emptyForm());
    setPersonSearch("");
    setFormError("");
    setShowForm(true);
  }

  function startEdit(u: UserEntry) {
    setEditId(u.id);
    setForm({
      email: u.email,
      is_active: u.is_active,
      person_id: u.person_id,
      role_codes: u.roles.map((r) => r.role_code),
    });
    const p = persons.find((p) => p.id === u.person_id);
    setPersonSearch(p ? personLabel(p) : "");
    setFormError("");
    setShowForm(true);
  }

  function toggleRole(code: string) {
    setForm((f) => ({
      ...f,
      role_codes: f.role_codes.includes(code)
        ? f.role_codes.filter((r) => r !== code)
        : [...f.role_codes, code],
    }));
  }

  const filteredPersons = personSearch.length >= 2
    ? persons.filter((p) =>
        personLabel(p).toLowerCase().includes(personSearch.toLowerCase())
      ).slice(0, 8)
    : [];

  function selectPerson(p: PersonOption) {
    setForm((f) => ({ ...f, person_id: p.id }));
    setPersonSearch(personLabel(p));
  }

  function clearPerson() {
    setForm((f) => ({ ...f, person_id: null }));
    setPersonSearch("");
  }

  async function save() {
    setSaving(true);
    setFormError("");
    try {
      const payload = {
        email: form.email.trim(),
        is_active: form.is_active,
        person_id: form.person_id,
        role_codes: form.role_codes,
      };
      if (editId !== null) {
        await updateAdminUser(editId, payload);
      } else {
        await createAdminUser(payload);
      }
      setShowForm(false);
      await load();
    } catch (e) {
      setFormError(parseApiError(e, "Opslaan mislukt."));
    } finally {
      setSaving(false);
    }
  }

  async function remove(u: UserEntry) {
    if (!confirm(`Gebruiker "${u.email}" verwijderen?`)) return;
    try {
      await deleteAdminUser(u.id);
      await load();
    } catch (e) {
      alert(parseApiError(e, "Verwijderen mislukt."));
    }
  }

  if (loading) return <p className="text-gray-500">Laden…</p>;
  if (error) return <p className="text-red-600">{error}</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-blue-900">Gebruikers</h2>
        <button className="btn-primary" onClick={startCreate}>+ Nieuwe gebruiker</button>
      </div>

      {showForm && (
        <div className="card mb-6">
          <h3 className="font-semibold text-blue-800 mb-4">{editId ? "Gebruiker bewerken" : "Nieuwe gebruiker"}</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium mb-1">E-mailadres</label>
              <input className="input w-full" type="email" value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Persoon (optioneel)</label>
              <div className="relative">
                <div className="flex gap-2">
                  <input
                    className="input flex-1"
                    placeholder="Zoek op naam of adres…"
                    value={personSearch}
                    onChange={(e) => {
                      setPersonSearch(e.target.value);
                      if (form.person_id !== null) setForm((f) => ({ ...f, person_id: null }));
                    }}
                  />
                  {form.person_id !== null && (
                    <button type="button" onClick={clearPerson}
                      className="text-xs text-gray-500 hover:text-red-600 px-2">✕</button>
                  )}
                </div>
                {filteredPersons.length > 0 && form.person_id === null && (
                  <ul className="absolute z-10 mt-1 w-full bg-white border rounded shadow-md text-sm max-h-48 overflow-y-auto">
                    {filteredPersons.map((p) => (
                      <li key={p.id}
                        className="px-3 py-2 hover:bg-blue-50 cursor-pointer"
                        onMouseDown={() => selectPerson(p)}>
                        {personLabel(p)}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {form.person_id !== null && (
                <p className="text-xs text-green-700 mt-1">Gekoppeld aan persoon #{form.person_id}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Rollen</label>
              <div className="flex gap-3">
                {ALL_ROLES.map((code) => (
                  <label key={code} className="flex items-center gap-1 text-sm cursor-pointer">
                    <input type="checkbox" checked={form.role_codes.includes(code)}
                      onChange={() => toggleRole(code)} />
                    {code}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.is_active}
                  onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
                Actief
              </label>
            </div>
            {formError && <p className="text-red-600 text-sm">{formError}</p>}
            <div className="flex gap-2">
              <button className="btn-primary" onClick={save} disabled={saving}>
                {saving ? "Opslaan…" : "Opslaan"}
              </button>
              <button className="btn-secondary" onClick={() => setShowForm(false)}>Annuleren</button>
            </div>
          </div>
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-3 font-medium">E-mail</th>
              <th className="text-left px-4 py-3 font-medium">Persoon</th>
              <th className="text-left px-4 py-3 font-medium">Rollen</th>
              <th className="text-left px-4 py-3 font-medium">Actief</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">{u.email}</td>
                <td className="px-4 py-3 text-gray-600">
                  {u.person
                    ? `${u.person.first_name} ${u.person.last_name}`
                    : <span className="italic text-gray-400">—</span>}
                </td>
                <td className="px-4 py-3">
                  {u.roles.length === 0 ? (
                    <span className="italic text-gray-400">—</span>
                  ) : u.roles.map((r) => (
                    <span key={r.role_code} className="inline-block mr-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
                      {r.role_code}
                    </span>
                  ))}
                </td>
                <td className="px-4 py-3">
                  {u.is_active
                    ? <span className="text-green-700 font-medium">Ja</span>
                    : <span className="text-gray-400">Nee</span>}
                </td>
                <td className="px-4 py-3 text-right space-x-2">
                  <button className="text-blue-600 hover:underline text-xs" onClick={() => startEdit(u)}>Bewerken</button>
                  <button className="text-red-600 hover:underline text-xs" onClick={() => remove(u)}>Verwijderen</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && (
          <p className="text-center text-gray-500 py-8 italic">Geen gebruikers gevonden.</p>
        )}
      </div>
    </div>
  );
}
