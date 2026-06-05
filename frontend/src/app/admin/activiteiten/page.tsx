"use client";
import { useEffect, useState } from "react";
import {
  getActivities, getArchivedActivities, createActivity, updateActivity, deleteActivity,
  getRegistrations, createSubRegistration, updateSubRegistration, deleteSubRegistration,
} from "@/lib/api";
import type { Activity, SubRegistration, Registration } from "@/lib/types";

const REG_FORM_TYPES = [
  { value: "NONE", label: "Geen formulier" },
  { value: "INDIVIDUAL", label: "Individueel" },
  { value: "GROUP", label: "Groep" },
  { value: "TEAM", label: "Team" },
  { value: "AGE_CATEGORY", label: "Leeftijdscategorie" },
  { value: "PAID_PER_PERSON", label: "Betaald per persoon" },
  { value: "PAID_PRODUCTS", label: "Betaalde producten" },
];

const emptyActivity = () => ({
  name: "", date: "", date_end: "", time: "", location: "", max_participants: "",
  registration_type_code: "INDIVIDUAL", price: "0", member_price: "", poster_url: "",
  is_archived: false, reg_form_type: "NONE",
});

const emptySub = () => ({
  name: "", description: "", external_register_url: "", external_registrations_url: "",
  info_url: "", is_free: true, price: "0", reg_form_type: "", sort_order: 0,
});

interface SubForm {
  name: string; description: string; external_register_url: string;
  external_registrations_url: string; info_url: string;
  is_free: boolean; price: string; reg_form_type: string; sort_order: number;
}

export default function AdminActiviteiten() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [archived, setArchived] = useState<Activity[]>([]);
  const [form, setForm] = useState(emptyActivity());
  const [editing, setEditing] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [registrations, setRegistrations] = useState<{ [id: number]: Registration[] }>({});
  const [viewRegs, setViewRegs] = useState<number | null>(null);
  const [tab, setTab] = useState<"upcoming" | "archived">("upcoming");
  const [expandedSubs, setExpandedSubs] = useState<number | null>(null);
  const [subForm, setSubForm] = useState<SubForm>(emptySub());
  const [editingSub, setEditingSub] = useState<number | null>(null);
  const [showSubForm, setShowSubForm] = useState<number | null>(null); // activity id

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
      date_end: form.date_end || null,
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
    setForm(emptyActivity());
    load();
  }

  function startEdit(a: Activity) {
    setForm({
      name: a.name, date: a.date, date_end: a.date_end || "", time: a.time || "",
      location: a.location || "", max_participants: a.max_participants?.toString() || "",
      registration_type_code: a.registration_type ?? "INDIVIDUAL",
      price: a.price.toString(),
      member_price: a.member_price?.toString() || "", poster_url: a.poster_url || "",
      is_archived: a.is_archived, reg_form_type: a.reg_form_type || "NONE",
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

  async function handleSubSubmit(activityId: number, e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      ...subForm,
      price: subForm.is_free ? "0" : subForm.price,
      reg_form_type: subForm.reg_form_type || null,
      description: subForm.description || null,
      external_register_url: subForm.external_register_url || null,
      external_registrations_url: subForm.external_registrations_url || null,
      info_url: subForm.info_url || null,
    };
    if (editingSub !== null) {
      await updateSubRegistration(activityId, editingSub, payload);
    } else {
      await createSubRegistration(activityId, payload);
    }
    setShowSubForm(null);
    setEditingSub(null);
    setSubForm(emptySub());
    load();
  }

  function startEditSub(activityId: number, sub: SubRegistration) {
    setSubForm({
      name: sub.name, description: sub.description || "", external_register_url: sub.external_register_url || "",
      external_registrations_url: sub.external_registrations_url || "", info_url: sub.info_url || "",
      is_free: sub.is_free, price: sub.price?.toString() || "0",
      reg_form_type: sub.reg_form_type || "", sort_order: sub.sort_order,
    });
    setEditingSub(sub.id);
    setShowSubForm(activityId);
  }

  async function handleDeleteSub(activityId: number, subId: number) {
    if (!confirm("Verwijder deze sub-registratie?")) return;
    await deleteSubRegistration(activityId, subId);
    load();
  }

  async function moveSub(activityId: number, subs: SubRegistration[], idx: number, dir: -1 | 1) {
    const target = subs[idx];
    const swap = subs[idx + dir];
    await Promise.all([
      updateSubRegistration(activityId, target.id, { sort_order: swap.sort_order }),
      updateSubRegistration(activityId, swap.id, { sort_order: target.sort_order }),
    ]);
    load();
  }

  const list = tab === "upcoming" ? activities : archived;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-blue-800">Activiteiten</h1>
        <button className="btn-primary btn-sm" onClick={() => { setShowForm(true); setEditing(null); setForm(emptyActivity()); }}>
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
                <label className="label">Startdatum *</label>
                <input type="date" className="input" required value={form.date} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} />
              </div>
              <div>
                <label className="label">Einddatum</label>
                <input type="date" className="input" value={form.date_end} onChange={(e) => setForm((f) => ({ ...f, date_end: e.target.value }))} />
              </div>
              <div>
                <label className="label">Tijdstip</label>
                <input type="time" className="input" value={form.time} onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))} />
              </div>
              <div>
                <label className="label">Max. deelnemers</label>
                <input type="number" className="input" value={form.max_participants} onChange={(e) => setForm((f) => ({ ...f, max_participants: e.target.value }))} />
              </div>
              <div className="sm:col-span-2">
                <label className="label">Locatie</label>
                <input className="input" value={form.location} onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))} />
              </div>
              <div>
                <label className="label">Inschrijvingsformulier</label>
                <select className="input" value={form.reg_form_type} onChange={(e) => setForm((f) => ({ ...f, reg_form_type: e.target.value }))}>
                  {REG_FORM_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
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
        {list.map((a) => {
          const subs = (a.sub_registrations ?? []).slice().sort((x, y) => x.sort_order - y.sort_order);
          const subsExpanded = expandedSubs === a.id;
          return (
            <div key={a.id} className="card">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{a.name}</div>
                  <div className="text-sm text-gray-600">{new Date(a.date).toLocaleDateString("nl-BE")} · {a.location}</div>
                  <div className="text-sm text-gray-500">{a.registration_count ?? 0} ingeschreven{a.max_participants ? ` / ${a.max_participants}` : ""}</div>
                </div>
                <div className="flex gap-2 flex-wrap justify-end">
                  <button className="btn-secondary btn-sm" onClick={() => loadRegistrations(a.id)}>Inschrijvingen</button>
                  <button
                    className={subsExpanded ? "btn-primary btn-sm" : "btn-secondary btn-sm"}
                    onClick={() => setExpandedSubs(subsExpanded ? null : a.id)}
                  >
                    Sub-registraties {subs.length > 0 ? `(${subs.length})` : ""}
                  </button>
                  <button className="btn-secondary btn-sm" onClick={() => startEdit(a)}>Bewerken</button>
                  <button className="btn-danger btn-sm" onClick={() => handleDelete(a.id)}>Verwijderen</button>
                </div>
              </div>

              {/* Registrations */}
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

              {/* Sub-registrations */}
              {subsExpanded && (
                <div className="mt-3 border-t pt-3">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-medium text-sm">Sub-registraties</span>
                    {showSubForm !== a.id && (
                      <button
                        className="btn-primary btn-sm"
                        onClick={() => { setSubForm(emptySub()); setEditingSub(null); setShowSubForm(a.id); }}
                      >
                        + Toevoegen
                      </button>
                    )}
                  </div>

                  {subs.length === 0 && showSubForm !== a.id && (
                    <p className="text-sm text-gray-500 mb-3">Nog geen sub-registraties.</p>
                  )}

                  {subs.length > 0 && (
                    <div className="space-y-2 mb-3">
                      {subs.map((sub, idx) => (
                        <div key={sub.id} className="flex items-center gap-2 bg-gray-50 rounded p-2 text-sm">
                          <div className="flex flex-col gap-0.5">
                            <button
                              className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none"
                              disabled={idx === 0}
                              onClick={() => moveSub(a.id, subs, idx, -1)}
                              title="Omhoog"
                            >▲</button>
                            <button
                              className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none"
                              disabled={idx === subs.length - 1}
                              onClick={() => moveSub(a.id, subs, idx, 1)}
                              title="Omlaag"
                            >▼</button>
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="font-medium">{sub.name}</span>
                            {sub.reg_form_type && (
                              <span className="ml-2 text-xs text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
                                {REG_FORM_TYPES.find((t) => t.value === sub.reg_form_type)?.label ?? sub.reg_form_type}
                              </span>
                            )}
                            {!sub.is_free && (
                              <span className="ml-2 text-xs text-green-700 bg-green-50 px-1.5 py-0.5 rounded">
                                €{parseFloat(sub.price).toFixed(2)}
                              </span>
                            )}
                            {sub.external_register_url && (
                              <span className="ml-2 text-xs text-gray-500">↗ extern</span>
                            )}
                          </div>
                          <button className="btn-secondary btn-sm" onClick={() => startEditSub(a.id, sub)}>Bewerken</button>
                          <button className="btn-danger btn-sm" onClick={() => handleDeleteSub(a.id, sub.id)}>×</button>
                        </div>
                      ))}
                    </div>
                  )}

                  {showSubForm === a.id && (
                    <form onSubmit={(e) => handleSubSubmit(a.id, e)} className="bg-blue-50 rounded-lg p-3 space-y-3">
                      <p className="font-medium text-sm">{editingSub !== null ? "Sub-registratie bewerken" : "Nieuwe sub-registratie"}</p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="sm:col-span-2">
                          <label className="label">Naam *</label>
                          <input className="input" required value={subForm.name} onChange={(e) => setSubForm((f) => ({ ...f, name: e.target.value }))} />
                        </div>
                        <div>
                          <label className="label">Inschrijvingsformulier</label>
                          <select className="input" value={subForm.reg_form_type} onChange={(e) => setSubForm((f) => ({ ...f, reg_form_type: e.target.value }))}>
                            <option value="">— geen intern formulier —</option>
                            {REG_FORM_TYPES.filter((t) => t.value !== "NONE").map((t) => (
                              <option key={t.value} value={t.value}>{t.label}</option>
                            ))}
                          </select>
                        </div>
                        <div className="flex items-center gap-2 pt-5">
                          <input type="checkbox" id={`is_free_${a.id}`} checked={subForm.is_free} onChange={(e) => setSubForm((f) => ({ ...f, is_free: e.target.checked }))} />
                          <label htmlFor={`is_free_${a.id}`}>Gratis</label>
                        </div>
                        {!subForm.is_free && (
                          <div>
                            <label className="label">Prijs (€)</label>
                            <input type="number" step="0.01" className="input" value={subForm.price} onChange={(e) => setSubForm((f) => ({ ...f, price: e.target.value }))} />
                          </div>
                        )}
                        <div>
                          <label className="label">Volgorde</label>
                          <input type="number" className="input" value={subForm.sort_order} onChange={(e) => setSubForm((f) => ({ ...f, sort_order: parseInt(e.target.value) || 0 }))} />
                        </div>
                        <div className="sm:col-span-2">
                          <label className="label">Externe inschrijvingslink</label>
                          <input className="input" placeholder="https://…" value={subForm.external_register_url} onChange={(e) => setSubForm((f) => ({ ...f, external_register_url: e.target.value }))} />
                        </div>
                        <div className="sm:col-span-2">
                          <label className="label">Externe inschrijvingenlink</label>
                          <input className="input" placeholder="https://…" value={subForm.external_registrations_url} onChange={(e) => setSubForm((f) => ({ ...f, external_registrations_url: e.target.value }))} />
                        </div>
                        <div className="sm:col-span-2">
                          <label className="label">Info URL (reglement)</label>
                          <input className="input" placeholder="https://…" value={subForm.info_url} onChange={(e) => setSubForm((f) => ({ ...f, info_url: e.target.value }))} />
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button type="submit" className="btn-primary btn-sm">Opslaan</button>
                        <button type="button" className="btn-secondary btn-sm" onClick={() => { setShowSubForm(null); setEditingSub(null); }}>Annuleren</button>
                      </div>
                    </form>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {list.length === 0 && <p className="text-gray-500 text-sm">Geen activiteiten.</p>}
      </div>
    </div>
  );
}
