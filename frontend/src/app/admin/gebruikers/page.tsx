"use client";
import { useEffect, useState } from "react";
import { getAdminUsers, createAdminUser, updateAdminUser, deleteAdminUser } from "@/lib/api";
import { parseApiError } from "@/lib/errors";

const ALL_ROLES = ["ADMIN", "MEMBER", "USER"];

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
  person_id: "",
  role_codes: [] as string[],
});

export default function AdminGebruikers() {
  const [users, setUsers] = useState<UserEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  async function load() {
    setLoading(true);
    try {
      const r = await getAdminUsers();
      setUsers(r.data);
    } catch (e) {
      setError(parseApiError(e, "Kon gebruikers niet laden."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function startCreate() {
    setEditId(null);
    setForm(emptyForm());
    setFormError("");
    setShowForm(true);
  }

  function startEdit(u: UserEntry) {
    setEditId(u.id);
    setForm({
      email: u.email,
      is_active: u.is_active,
      person_id: u.person_id != null ? String(u.person_id) : "",
      role_codes: u.roles.map((r) => r.role_code),
    });
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

  async function save() {
    setSaving(true);
    setFormError("");
    try {
      const payload = {
        email: form.email.trim(),
        is_active: form.is_active,
        person_id: form.person_id !== "" ? Number(form.person_id) : null,
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
              <label className="block text-sm font-medium mb-1">Persoon-ID (optioneel)</label>
              <input className="input w-full" type="number" placeholder="bijv. 42"
                value={form.person_id}
                onChange={(e) => setForm((f) => ({ ...f, person_id: e.target.value }))} />
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
                  {u.person ? `${u.person.first_name} ${u.person.last_name} (#${u.person.id})` : <span className="italic text-gray-400">—</span>}
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
                  {u.is_active ? (
                    <span className="text-green-700 font-medium">Ja</span>
                  ) : (
                    <span className="text-gray-400">Nee</span>
                  )}
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
