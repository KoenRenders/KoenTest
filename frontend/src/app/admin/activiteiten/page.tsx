"use client";
import { useEffect, useState } from "react";
import { getActivities, getArchivedActivities, createActivity, updateActivity, deleteActivity, getRegistrations } from "@/lib/api";
import type { Activity, Registration } from "@/lib/types";

const empty = () => ({
  name: "", date: "", time: "", location: "", max_participants: "", registration_type: "individual",
  price: "0", member_price: "", poster_url: "", is_archived: false,
});

export default function AdminActiviteiten() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [archived, setArchived] = useState<Activity[]>([]);
  const [form, setForm] = useState(empty());
  const [editing, setEditing] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [registrations, setRegistrations] = useState<{ [id: number]: Registration[] }>({});
  const [viewRegs, setViewRegs] = useState<number | null>(null);
  const [tab, setTab] = useState<"upcoming" | "archived">("upcoming");

  function load() {
    getActivities().then((r) => setActivities(r.data)).catch(() => {});
    getArchivedActivities().then((r) => setArchived(r.data)).catch(() => {});
  }

  useEffect(() => { load(); }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      ...form,
      time: form.time || null,
      location: form.location || null,
      max_participants: form.max_participants ? parseInt(form.max_participants) : null,
      member_price: form.member_price ? form.member_price : null,
      poster_url: form.poster_url || null,
    };
    if (editing !== null) {
      await updateActivity(editing, payload);
    } else {
      await createActivity(payload);
    }
    setShowForm(false);
    setEditing(null);
    setForm(empty());
    load();
  }

  function startEdit(a: Activity) {
    setForm({
      name: a.name, date: a.date, time: a.time || "", location: a.location || "",
      max_participants: a.max_participants?.toString() || "",
      registration_type: a.registration_type, price: a.price.toString(),
      member_price: a.member_price?.toString() || "", poster_url: a.poster_url || "",
      is_archived: a.is_archived,
    });
    setEditing(a.id);
    setShowForm(true);
  }

  async function handleDelete(id: number) {
    if (!confirm("Verwijder deze activiteit?")) return;
    await deleteActivity(id);
    load();
  }

  async function loadRegistrations(id: number) {
    const r = await getRegistrations(id);
    setRegistrations((prev) => ({ ...prev, [id]: r.data }));
    setViewRegs(id);
  }

  const list = tab === "upcoming" ? activities : archived;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-blue-800">Activiteiten</h1>
        <button className="btn-primary btn-sm" onClick={() => { setShowForm(true); setEditing(null); setForm(empty()); }}>
          + Nieuwe activiteit
        </button>
      </div>

      {showForm && (
        <div className="card mb-6">
          <h2 className="font-bold text-lg mb-4">{editing !== null ? "Activiteit bewerken" : "Nieuwe activiteit"}</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <label className="label">Naam *</label>
                <input className="input" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
              </div>
              <div>
                <label className="label">Datum *</label>
                <input type="date" className="input" required value={form.date} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} />
              </div>
              <div>
                <label className="label">Tijdstip</label>
                <input type="time" className="input" value={form.time} onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))} />
              </div>
              <div className="sm:col-span-2">
                <label className="label">Locatie</label>
                <input className="input" value={form.location} onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))} />
              </div>
              <div>
                <label className="label">Max. deelnemers</label>
                <input type="number" className="input" value={form.max_participants} onChange={(e) => setForm((f) => ({ ...f, max_participants: e.target.value }))} />
              </div>
              <div>
                <label className="label">Inschrijvingstype</label>
                <select className="input" value={form.registration_type} onChange={(e) => setForm((f) => ({ ...f, registration_type: e.target.value }))}>
                  <option value="individual">Per persoon</option>
                  <option value="family">Per gezin</option>
                </select>
              </div>
              <div>
                <label className="label">Prijs (€)</label>
                <input type="number" step="0.01" className="input" value={form.price} onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))} />
              </div>
              <div>
                <label className="label">Ledenprijs (€)</label>
                <input type="number" step="0.01" className="input" value={form.member_price} onChange={(e) => setForm((f) => ({ ...f, member_price: e.target.value }))} />
              </div>
              <div className="sm:col-span-2">
                <label className="label">Affiche URL</label>
                <input className="input" value={form.poster_url} onChange={(e) => setForm((f) => ({ ...f, poster_url: e.target.value }))} />
              </div>
              {editing !== null && (
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="archived" checked={form.is_archived} onChange={(e) => setForm((f) => ({ ...f, is_archived: e.target.checked }))} />
                  <label htmlFor="archived">Gearchiveerd</label>
                </div>
              )}
            </div>
            <div className="flex gap-3">
              <button type="submit" className="btn-primary">Opslaan</button>
              <button type="button" className="btn-secondary" onClick={() => { setShowForm(false); setEditing(null); }}>Annuleren</button>
            </div>
          </form>
        </div>
      )}

      <div className="flex gap-2 mb-4">
        <button className={tab === "upcoming" ? "btn-primary btn-sm" : "btn-secondary btn-sm"} onClick={() => setTab("upcoming")}>Komend</button>
        <button className={tab === "archived" ? "btn-primary btn-sm" : "btn-secondary btn-sm"} onClick={() => setTab("archived")}>Archief</button>
      </div>

      <div className="space-y-3">
        {list.map((a) => (
          <div key={a.id} className="card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold">{a.name}</div>
                <div className="text-sm text-gray-600">{new Date(a.date).toLocaleDateString("nl-BE")} · {a.location}</div>
                <div className="text-sm text-gray-500">{a.registration_count ?? 0} ingeschreven{a.max_participants ? ` / ${a.max_participants}` : ""}</div>
              </div>
              <div className="flex gap-2 flex-wrap">
                <button className="btn-secondary btn-sm" onClick={() => loadRegistrations(a.id)}>Inschrijvingen</button>
                <button className="btn-secondary btn-sm" onClick={() => startEdit(a)}>Bewerken</button>
                <button className="btn-danger btn-sm" onClick={() => handleDelete(a.id)}>Verwijderen</button>
              </div>
            </div>
            {viewRegs === a.id && registrations[a.id] && (
              <div className="mt-3 border-t pt-3">
                <div className="flex justify-between mb-2">
                  <span className="font-medium text-sm">Inschrijvingen ({registrations[a.id].length})</span>
                  <button onClick={() => setViewRegs(null)} className="text-sm text-gray-500 hover:underline">Sluiten</button>
                </div>
                {registrations[a.id].length === 0 ? (
                  <p className="text-sm text-gray-500">Geen inschrijvingen.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="text-left text-gray-500"><th className="pb-1 pr-4">Naam</th><th className="pb-1 pr-4">E-mail</th><th className="pb-1">Datum</th></tr></thead>
                      <tbody>
                        {registrations[a.id].map((r) => (
                          <tr key={r.id}>
                            <td className="pr-4 py-1">{r.contact_name || `Gezin #${r.family_id}`}</td>
                            <td className="pr-4 py-1">{r.contact_email || "—"}</td>
                            <td className="py-1">{new Date(r.registered_at).toLocaleDateString("nl-BE")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {list.length === 0 && <p className="text-gray-500 text-sm">Geen activiteiten.</p>}
      </div>
    </div>
  );
}
