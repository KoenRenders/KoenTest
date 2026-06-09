"use client";
import { useEffect, useState } from "react";
import {
  getActivities, getArchivedActivities, createActivity, updateActivity, deleteActivity,
  getRegistrations, createSubRegistration, updateSubRegistration, deleteSubRegistration,
} from "@/lib/api";
import type { Activity, SubRegistration, Registration } from "@/lib/types";

const emptyActivity = () => ({
  name: "", date: "", date_end: "", time: "", location: "", max_participants: "",
  poster_url: "", is_archived: false, team_name_required: false,
});

const emptyProduct = () => ({
  name: "", description: "", external_register_url: "", external_registrations_url: "",
  info_url: "", is_free: true, price: "0", member_price: "", sort_order: 0,
});

interface ProductForm {
  name: string; description: string; external_register_url: string;
  external_registrations_url: string; info_url: string;
  is_free: boolean; price: string; member_price: string; sort_order: number;
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
  const [expandedProducts, setExpandedProducts] = useState<number | null>(null);
  const [productForm, setProductForm] = useState<ProductForm>(emptyProduct());
  const [editingProduct, setEditingProduct] = useState<number | null>(null);
  const [showProductForm, setShowProductForm] = useState<number | null>(null);

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
      poster_url: form.poster_url || null,
      price: 0,
    };
    try {
      if (editing !== null) {
        await updateActivity(editing, payload);
      } else {
        await createActivity(payload);
      }
      setShowForm(false);
      setEditing(null);
      setForm(emptyActivity());
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(msg || "Opslaan mislukt.");
    }
  }

  function startEdit(a: Activity) {
    setForm({
      name: a.name, date: a.date, date_end: a.date_end || "", time: a.time || "",
      location: a.location || "", max_participants: a.max_participants?.toString() || "",
      poster_url: a.poster_url || "", is_archived: a.is_archived,
      team_name_required: a.team_name_required ?? false,
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

  async function handleProductSubmit(activityId: number, e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      ...productForm,
      price: productForm.is_free ? "0" : productForm.price,
      member_price: productForm.is_free ? null : (productForm.member_price || null),
      description: productForm.description || null,
      external_register_url: productForm.external_register_url || null,
      external_registrations_url: productForm.external_registrations_url || null,
      info_url: productForm.info_url || null,
    };
    if (editingProduct !== null) {
      await updateSubRegistration(activityId, editingProduct, payload);
    } else {
      await createSubRegistration(activityId, payload);
    }
    setShowProductForm(null);
    setEditingProduct(null);
    setProductForm(emptyProduct());
    load();
  }

  function startEditProduct(activityId: number, sub: SubRegistration) {
    setProductForm({
      name: sub.name, description: sub.description || "",
      external_register_url: sub.external_register_url || "",
      external_registrations_url: sub.external_registrations_url || "",
      info_url: sub.info_url || "",
      is_free: sub.is_free, price: sub.price?.toString() || "0",
      member_price: sub.member_price?.toString() || "",
      sort_order: sub.sort_order,
    });
    setEditingProduct(sub.id);
    setShowProductForm(activityId);
  }

  async function handleDeleteProduct(activityId: number, subId: number) {
    if (!confirm("Verwijder dit product?")) return;
    await deleteSubRegistration(activityId, subId);
    load();
  }

  async function moveProduct(activityId: number, subs: SubRegistration[], idx: number, dir: -1 | 1) {
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
              <div className="sm:col-span-2">
                <label className="label">Affiche URL</label>
                <input className="input" value={form.poster_url} onChange={(e) => setForm((f) => ({ ...f, poster_url: e.target.value }))} />
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="team_name_required" checked={form.team_name_required}
                  onChange={(e) => setForm((f) => ({ ...f, team_name_required: e.target.checked }))} />
                <label htmlFor="team_name_required">Ploegnaam vereist?</label>
              </div>
              {editing !== null && (
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="archived" checked={form.is_archived}
                    onChange={(e) => setForm((f) => ({ ...f, is_archived: e.target.checked }))} />
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
          const products = (a.sub_registrations ?? []).slice().sort((x, y) => x.sort_order - y.sort_order);
          const productsExpanded = expandedProducts === a.id;
          return (
            <div key={a.id} className="card">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{a.name}</div>
                  <div className="text-sm text-gray-600">{new Date(a.date).toLocaleDateString("nl-BE")} · {a.location}</div>
                  <div className="text-sm text-gray-500">
                    {a.registration_count ?? 0} ingeschreven{a.max_participants ? ` / ${a.max_participants}` : ""}
                    {a.team_name_required && <span className="ml-2 text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">ploegnaam</span>}
                  </div>
                </div>
                <div className="flex gap-2 flex-wrap justify-end">
                  <button className="btn-secondary btn-sm" onClick={() => loadRegistrations(a.id)}>Inschrijvingen</button>
                  <button
                    className={productsExpanded ? "btn-primary btn-sm" : "btn-secondary btn-sm"}
                    onClick={() => setExpandedProducts(productsExpanded ? null : a.id)}
                  >
                    Producten {products.length > 0 ? `(${products.length})` : ""}
                  </button>
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
                        <thead><tr className="text-left text-gray-500"><th className="pb-1 pr-4">Naam</th><th className="pb-1 pr-4">Ploeg</th><th className="pb-1 pr-4">E-mail</th><th className="pb-1">Datum</th></tr></thead>
                        <tbody>
                          {registrations[a.id].map((r) => (
                            <tr key={r.id}>
                              <td className="pr-4 py-1">{r.contact_name || `Gezin #${r.family_id}`}</td>
                              <td className="pr-4 py-1">{(r as unknown as { team_name?: string }).team_name || "—"}</td>
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

              {productsExpanded && (
                <div className="mt-3 border-t pt-3">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-medium text-sm">Producten</span>
                    {showProductForm !== a.id && (
                      <button className="btn-primary btn-sm"
                        onClick={() => { setProductForm(emptyProduct()); setEditingProduct(null); setShowProductForm(a.id); }}>
                        + Toevoegen
                      </button>
                    )}
                  </div>

                  {products.length === 0 && showProductForm !== a.id && (
                    <p className="text-sm text-gray-500 mb-3">Nog geen producten.</p>
                  )}

                  {products.length > 0 && (
                    <div className="space-y-2 mb-3">
                      {products.map((p, idx) => (
                        <div key={p.id} className="flex items-center gap-2 bg-gray-50 rounded p-2 text-sm">
                          <div className="flex flex-col gap-0.5">
                            <button className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none"
                              disabled={idx === 0} onClick={() => moveProduct(a.id, products, idx, -1)}>▲</button>
                            <button className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none"
                              disabled={idx === products.length - 1} onClick={() => moveProduct(a.id, products, idx, 1)}>▼</button>
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="font-medium">{p.name}</span>
                            {p.is_free
                              ? <span className="ml-2 text-xs text-green-700 bg-green-50 px-1.5 py-0.5 rounded">Gratis</span>
                              : <span className="ml-2 text-xs text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">
                                  €{parseFloat(p.price).toFixed(2)}
                                  {p.member_price ? ` / leden €${parseFloat(p.member_price).toFixed(2)}` : ""}
                                </span>
                            }
                            {p.external_register_url && <span className="ml-2 text-xs text-gray-500">↗ extern</span>}
                          </div>
                          <button className="btn-secondary btn-sm" onClick={() => startEditProduct(a.id, p)}>Bewerken</button>
                          <button className="btn-danger btn-sm" onClick={() => handleDeleteProduct(a.id, p.id)}>×</button>
                        </div>
                      ))}
                    </div>
                  )}

                  {showProductForm === a.id && (
                    <form onSubmit={(e) => handleProductSubmit(a.id, e)} className="bg-blue-50 rounded-lg p-3 space-y-3">
                      <p className="font-medium text-sm">{editingProduct !== null ? "Product bewerken" : "Nieuw product"}</p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="sm:col-span-2">
                          <label className="label">Naam *</label>
                          <input className="input" required value={productForm.name}
                            onChange={(e) => setProductForm((f) => ({ ...f, name: e.target.value }))} />
                        </div>
                        <div className="flex items-center gap-2 pt-1">
                          <input type="checkbox" id={`is_free_${a.id}`} checked={productForm.is_free}
                            onChange={(e) => setProductForm((f) => ({ ...f, is_free: e.target.checked }))} />
                          <label htmlFor={`is_free_${a.id}`}>Gratis</label>
                        </div>
                        {!productForm.is_free && (
                          <>
                            <div>
                              <label className="label">Prijs niet-leden (€)</label>
                              <input type="number" step="0.01" className="input" value={productForm.price}
                                onChange={(e) => setProductForm((f) => ({ ...f, price: e.target.value }))} />
                            </div>
                            <div>
                              <label className="label">Ledenprijs (€, optioneel)</label>
                              <input type="number" step="0.01" className="input" value={productForm.member_price}
                                onChange={(e) => setProductForm((f) => ({ ...f, member_price: e.target.value }))} />
                            </div>
                          </>
                        )}
                        <div>
                          <label className="label">Max. deelnemers (optioneel)</label>
                          <input type="number" className="input" value={""}
                            onChange={() => {}} placeholder="onbeperkt" />
                        </div>
                        <div>
                          <label className="label">Volgorde</label>
                          <input type="number" className="input" value={productForm.sort_order}
                            onChange={(e) => setProductForm((f) => ({ ...f, sort_order: parseInt(e.target.value) || 0 }))} />
                        </div>
                        <div className="sm:col-span-2">
                          <label className="label">Externe inschrijvingslink (optioneel)</label>
                          <input className="input" placeholder="https://…" value={productForm.external_register_url}
                            onChange={(e) => setProductForm((f) => ({ ...f, external_register_url: e.target.value }))} />
                        </div>
                        <div className="sm:col-span-2">
                          <label className="label">Link om inschrijvingen te bekijken (optioneel)</label>
                          <input className="input" placeholder="https://…" value={productForm.external_registrations_url}
                            onChange={(e) => setProductForm((f) => ({ ...f, external_registrations_url: e.target.value }))} />
                        </div>
                        <div className="sm:col-span-2">
                          <label className="label">Info/reglement URL (optioneel)</label>
                          <input className="input" placeholder="https://…" value={productForm.info_url}
                            onChange={(e) => setProductForm((f) => ({ ...f, info_url: e.target.value }))} />
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button type="submit" className="btn-primary btn-sm">Opslaan</button>
                        <button type="button" className="btn-secondary btn-sm"
                          onClick={() => { setShowProductForm(null); setEditingProduct(null); }}>Annuleren</button>
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
