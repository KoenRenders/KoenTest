"use client";
import { useEffect, useState } from "react";
import {
  getActivities, getArchivedActivities, createActivity, updateActivity, deleteActivity,
  getRegistrations, addComponent, updateComponent, deleteComponent,
  addProduct, updateProduct, deleteProduct,
} from "@/lib/api";
import type { Activity, ActivityComponent, ActivityProduct } from "@/lib/types";
import { parseApiError } from "@/lib/errors";
import RegistrationList, { type RegistrationEntry } from "@/components/RegistrationList";

const emptyActivity = () => ({
  name: "", date: "", date_end: "", time: "", time_end: "", location: "",
  poster_url: "", is_cancelled: false,
});

const emptyComponent = () => ({
  name: "", team_name_required: false, sort_order: 0,
  external_register_url: "", external_registrations_url: "", info_url: "",
  max_participants: "",
});

const emptyProduct = () => ({
  name: "", is_free: true, price: "0", member_price: "", max_participants: "", sort_order: 0,
});


export default function AdminActiviteiten() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [archived, setArchived] = useState<Activity[]>([]);
  const [tab, setTab] = useState<"upcoming" | "archived">("upcoming");

  const [showActivityForm, setShowActivityForm] = useState(false);
  const [editingActivity, setEditingActivity] = useState<number | null>(null);
  const [activityForm, setActivityForm] = useState(emptyActivity());
  const [activityError, setActivityError] = useState<string | null>(null);
  const [savingActivity, setSavingActivity] = useState(false);

  const [showComponentForm, setShowComponentForm] = useState<number | null>(null);
  const [editingComponent, setEditingComponent] = useState<number | null>(null);
  const [componentForm, setComponentForm] = useState(emptyComponent());

  const [expandedComponent, setExpandedComponent] = useState<number | null>(null);
  const [showProductForm, setShowProductForm] = useState<number | null>(null);
  const [editingProduct, setEditingProduct] = useState<number | null>(null);
  const [productForm, setProductForm] = useState(emptyProduct());

  interface RegItem { product_id: number; quantity: number; product_name?: string; component_name?: string; }
  interface Reg { id: number; component_id?: number; contact_name?: string; contact_email?: string; phone?: string; team_name?: string; payment_method?: string; remarks?: string; items: RegItem[]; }
  const [registrations, setRegistrations] = useState<{ [id: number]: Reg[] }>({});
  const [viewRegs, setViewRegs] = useState<{ activityId: number; componentId: number | null } | null>(null);

  function load() {
    getActivities().then((r) => setActivities(r.data)).catch(() => {});
    getArchivedActivities().then((r) => setArchived(r.data)).catch(() => {});
  }

  useEffect(() => { load(); }, []);

  async function handleActivitySubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      name: activityForm.name,
      date: activityForm.date,
      date_end: activityForm.date_end || null,
      time: activityForm.time || null,
      time_end: activityForm.time_end || null,
      location: activityForm.location || null,
      poster_url: activityForm.poster_url || null,
      is_cancelled: activityForm.is_cancelled,
    };
    setActivityError(null);
    setSavingActivity(true);
    try {
      if (editingActivity !== null) {
        await updateActivity(editingActivity, payload);
      } else {
        await createActivity(payload);
      }
      setShowActivityForm(false);
      setEditingActivity(null);
      setActivityForm(emptyActivity());
      load();
    } catch (err) {
      setActivityError(parseApiError(err, "Opslaan van de activiteit is mislukt."));
    } finally {
      setSavingActivity(false);
    }
  }

  function startEditActivity(a: Activity) {
    setActivityForm({
      name: a.name, date: a.date, date_end: a.date_end || "",
      time: a.time || "", time_end: a.time_end || "", location: a.location || "",
      poster_url: a.poster_url || "",
      is_cancelled: a.is_cancelled ?? false,
    });
    setEditingActivity(a.id);
    setActivityError(null);
    setShowActivityForm(true);
  }

  async function handleDeleteActivity(id: number) {
    if (!confirm("Verwijder deze activiteit?")) return;
    await deleteActivity(id);
    load();
  }

  async function loadRegistrations(activityId: number, componentId: number | null) {
    const r = await getRegistrations(activityId);
    setRegistrations((prev) => ({ ...prev, [activityId]: r.data }));
    setViewRegs({ activityId, componentId });
  }

  async function handleComponentSubmit(e: React.FormEvent, activityId: number) {
    e.preventDefault();
    const payload = {
      ...componentForm,
      external_register_url: componentForm.external_register_url || null,
      external_registrations_url: componentForm.external_registrations_url || null,
      info_url: componentForm.info_url || null,
      max_participants: componentForm.max_participants ? parseInt(componentForm.max_participants) : null,
    };
    if (editingComponent !== null) {
      await updateComponent(activityId, editingComponent, payload);
    } else {
      const activity = activities.find(a => a.id === activityId) ?? archived.find(a => a.id === activityId);
      const nextOrder = (activity?.sub_registrations ?? []).length;
      await addComponent(activityId, { ...payload, sort_order: nextOrder });
    }
    setShowComponentForm(null);
    setEditingComponent(null);
    setComponentForm(emptyComponent());
    load();
  }

  function startEditComponent(activityId: number, c: ActivityComponent) {
    setComponentForm({
      name: c.name, team_name_required: c.team_name_required, sort_order: c.sort_order,
      external_register_url: c.external_register_url || "",
      external_registrations_url: c.external_registrations_url || "",
      info_url: c.info_url || "",
      max_participants: c.max_participants?.toString() || "",
    });
    setEditingComponent(c.id);
    setShowComponentForm(activityId);
  }

  async function handleDeleteComponent(activityId: number, componentId: number) {
    if (!confirm("Verwijder dit onderdeel?")) return;
    await deleteComponent(activityId, componentId);
    load();
  }

  async function handleProductSubmit(e: React.FormEvent, activityId: number, componentId: number) {
    e.preventDefault();
    const payload = {
      name: productForm.name,
      is_free: productForm.is_free,
      price: productForm.is_free ? "0" : productForm.price,
      member_price: productForm.member_price || null,
      max_participants: productForm.max_participants ? parseInt(productForm.max_participants) : null,
      sort_order: productForm.sort_order,
    };
    if (editingProduct !== null) {
      await updateProduct(activityId, componentId, editingProduct, payload);
    } else {
      const activity = activities.find(a => a.id === activityId) ?? archived.find(a => a.id === activityId);
      const component = (activity?.sub_registrations ?? []).find(c => c.id === componentId);
      const nextOrder = (component?.products ?? []).length;
      await addProduct(activityId, componentId, { ...payload, sort_order: nextOrder });
    }
    setShowProductForm(null);
    setEditingProduct(null);
    setProductForm(emptyProduct());
    load();
  }

  function startEditProduct(activityId: number, componentId: number, p: ActivityProduct) {
    setProductForm({
      name: p.name, is_free: p.is_free, price: p.price.toString(),
      member_price: p.member_price?.toString() || "",
      max_participants: p.max_participants?.toString() || "",
      sort_order: p.sort_order,
    });
    setEditingProduct(p.id);
    setExpandedComponent(componentId);
    setShowProductForm(componentId);
  }

  async function handleDeleteProduct(activityId: number, componentId: number, productId: number) {
    if (!confirm("Verwijder dit product?")) return;
    await deleteProduct(activityId, componentId, productId);
    load();
  }

  async function moveComponent(activityId: number, components: ActivityComponent[], idx: number, dir: -1 | 1) {
    const reordered = [...components];
    [reordered[idx], reordered[idx + dir]] = [reordered[idx + dir], reordered[idx]];
    // Normaliseer sort_order naar de nieuwe positie voor elk gewijzigd item.
    // Zelfherstellend: werkt ook als bestaande data allemaal sort_order 0 heeft.
    await Promise.all(
      reordered
        .map((c, i) => ({ c, i }))
        .filter(({ c, i }) => c.sort_order !== i)
        .map(({ c, i }) => updateComponent(activityId, c.id, { sort_order: i }))
    );
    load();
  }

  async function moveProduct(activityId: number, componentId: number, products: ActivityProduct[], idx: number, dir: -1 | 1) {
    const reordered = [...products];
    [reordered[idx], reordered[idx + dir]] = [reordered[idx + dir], reordered[idx]];
    await Promise.all(
      reordered
        .map((p, i) => ({ p, i }))
        .filter(({ p, i }) => p.sort_order !== i)
        .map(({ p, i }) => updateProduct(activityId, componentId, p.id, { sort_order: i }))
    );
    load();
  }

  const list = tab === "upcoming" ? activities : archived;

  return (
    <div>
<div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-blue-800">Activiteiten</h1>
        <button className="btn-primary btn-sm" onClick={() => { setShowActivityForm(true); setEditingActivity(null); setActivityForm(emptyActivity()); setActivityError(null); }}>
          + Nieuwe activiteit
        </button>
      </div>

      {showActivityForm && (
        <div className="card mb-6">
          <h2 className="font-bold text-lg mb-4">{editingActivity !== null ? "Activiteit bewerken" : "Nieuwe activiteit"}</h2>
          <form onSubmit={handleActivitySubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <label className="label">Naam *</label>
                <input className="input" required value={activityForm.name} onChange={(e) => setActivityForm((f) => ({ ...f, name: e.target.value }))} />
              </div>
              <div>
                <label className="label">Startdatum *</label>
                <input type="date" className="input" required value={activityForm.date} onChange={(e) => setActivityForm((f) => ({ ...f, date: e.target.value }))} />
              </div>
              <div>
                <label className="label">Einddatum</label>
                <input type="date" className="input" value={activityForm.date_end} onChange={(e) => setActivityForm((f) => ({ ...f, date_end: e.target.value }))} />
              </div>
              <div>
                <label className="label">Tijdstip</label>
                <input type="time" className="input" value={activityForm.time} onChange={(e) => setActivityForm((f) => ({ ...f, time: e.target.value }))} />
              </div>
              <div>
                <label className="label">Eindtijdstip</label>
                <input type="time" className="input" value={activityForm.time_end} onChange={(e) => setActivityForm((f) => ({ ...f, time_end: e.target.value }))} />
              </div>
              <div>
                <label className="label">Locatie</label>
                <input className="input" value={activityForm.location} onChange={(e) => setActivityForm((f) => ({ ...f, location: e.target.value }))} />
              </div>
              <div>
                <label className="label">Poster URL</label>
                <input className="input" value={activityForm.poster_url} onChange={(e) => setActivityForm((f) => ({ ...f, poster_url: e.target.value }))} />
              </div>
              <div className="flex items-center gap-2 pt-5">
                <input type="checkbox" id="is_cancelled" checked={activityForm.is_cancelled} onChange={(e) => setActivityForm((f) => ({ ...f, is_cancelled: e.target.checked }))} />
                <label htmlFor="is_cancelled">Geannuleerd</label>
              </div>
            </div>
            {activityError && (
              <p className="text-red-600 text-sm" role="alert">{activityError}</p>
            )}
            <div className="flex gap-3">
              <button type="submit" className="btn-primary" disabled={savingActivity}>
                {savingActivity ? "Opslaan…" : "Opslaan"}
              </button>
              <button type="button" className="btn-secondary" onClick={() => { setShowActivityForm(false); setEditingActivity(null); setActivityError(null); }}>Annuleren</button>
            </div>
          </form>
        </div>
      )}

      {viewRegs !== null && (() => {
        const { activityId, componentId } = viewRegs;
        const allRegs = registrations[activityId] ?? [];
        const regs = componentId !== null
          ? allRegs.filter((r) => r.component_id === componentId)
          : allRegs;
        const activity = [...activities, ...archived].find((a) => a.id === activityId);
        const component = componentId !== null
          ? activity?.sub_registrations?.find((c) => c.id === componentId)
          : null;

        // Product totals summary
        const productTotals: Record<string, number> = {};
        for (const r of regs) {
          for (const it of r.items) {
            const key = it.product_name ?? `Product ${it.product_id}`;
            productTotals[key] = (productTotals[key] ?? 0) + it.quantity;
          }
        }
        const hasTotals = Object.keys(productTotals).length > 0;

        const entries: RegistrationEntry[] = regs.map((r) => ({
          contact_name: r.contact_name,
          contact_email: r.contact_email,
          phone: r.phone,
          team_name: r.team_name,
          payment_method: r.payment_method,
          remarks: r.remarks,
          items: r.items.map((it) => ({
            product_name: it.product_name,
            quantity: it.quantity,
          })),
        }));

        return (
          <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-xl max-w-xl w-full p-6 max-h-[85vh] overflow-y-auto">
              <h2 className="font-bold text-lg mb-1">Inschrijvingen</h2>
              <p className="text-sm text-gray-500 mb-1">{activity?.name}</p>
              {component && <p className="text-sm font-medium text-blue-700 mb-3">{component.name}</p>}
              {hasTotals && (
                <div className="text-xs text-gray-500 bg-gray-50 rounded px-3 py-2 mb-3">
                  {Object.entries(productTotals).map(([name, qty]) => `${name}: ${qty}`).join(" · ")}
                </div>
              )}
              <RegistrationList entries={entries} />
              <button className="btn-secondary mt-4" onClick={() => setViewRegs(null)}>Sluiten</button>
            </div>
          </div>
        );
      })()}

      <div className="flex gap-2 mb-4">
        <button className={tab === "upcoming" ? "btn-primary btn-sm" : "btn-secondary btn-sm"} onClick={() => setTab("upcoming")}>Komende</button>
        <button className={tab === "archived" ? "btn-primary btn-sm" : "btn-secondary btn-sm"} onClick={() => setTab("archived")}>Archief</button>
      </div>

      <div className="space-y-4">
        {list.map((a) => (
          <div key={a.id} className="card">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <span className="font-semibold text-gray-900">{a.name}</span>
                <span className="ml-2 text-sm text-gray-500">{a.date}{a.date_end ? ` – ${a.date_end}` : ""}</span>
                {a.location && <span className="ml-2 text-sm text-gray-400">📍 {a.location}</span>}
              </div>
              <div className="flex gap-2 flex-wrap">
                {(a.sub_registrations?.length ?? 0) === 0 && (
                  <button className="btn-secondary btn-sm" onClick={() => loadRegistrations(a.id, null)}>Inschrijvingen</button>
                )}
                <button className="btn-secondary btn-sm" onClick={() => startEditActivity(a)}>Bewerken</button>
                <button className="btn-danger btn-sm" onClick={() => handleDeleteActivity(a.id)}>Verwijderen</button>
              </div>
            </div>

            <div className="mt-4 border-t pt-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm text-gray-700">Onderdelen</span>
                  <button className="btn-secondary btn-sm text-xs" onClick={() => { setShowComponentForm(a.id); setEditingComponent(null); setComponentForm(emptyComponent()); }}>
                    + Onderdeel
                  </button>
                </div>

                {showComponentForm === a.id && (
                  <form onSubmit={(e) => handleComponentSubmit(e, a.id)} className="bg-gray-50 rounded-lg p-3 space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="label">Naam *</label>
                        <input className="input" required value={componentForm.name} onChange={(e) => setComponentForm((f) => ({ ...f, name: e.target.value }))} />
                      </div>
                      <div className="flex items-center gap-2 pt-5">
                        <input type="checkbox" id={`tnr-${a.id}`} checked={componentForm.team_name_required}
                          onChange={(e) => setComponentForm((f) => ({ ...f, team_name_required: e.target.checked }))} />
                        <label htmlFor={`tnr-${a.id}`}>Ploegnaam vereist</label>
                      </div>
                      <div>
                        <label className="label">Externe inschrijvingslink</label>
                        <input className="input" type="url" value={componentForm.external_register_url}
                          onChange={(e) => setComponentForm((f) => ({ ...f, external_register_url: e.target.value }))}
                          placeholder="https://forms.gle/…" />
                      </div>
                      <div>
                        <label className="label">Link inschrijvingen bekijken</label>
                        <input className="input" type="url" value={componentForm.external_registrations_url}
                          onChange={(e) => setComponentForm((f) => ({ ...f, external_registrations_url: e.target.value }))}
                          placeholder="https://docs.google.com/…" />
                      </div>
                      <div className="sm:col-span-2">
                        <label className="label">Info/reglement URL</label>
                        <input className="input" type="url" value={componentForm.info_url}
                          onChange={(e) => setComponentForm((f) => ({ ...f, info_url: e.target.value }))}
                          placeholder="https://drive.google.com/…" />
                      </div>
                      <div>
                        <label className="label">Max. deelnemers</label>
                        <input className="input" type="number" min="1" value={componentForm.max_participants}
                          onChange={(e) => setComponentForm((f) => ({ ...f, max_participants: e.target.value }))}
                          placeholder="onbeperkt" />
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button type="submit" className="btn-primary btn-sm">Opslaan</button>
                      <button type="button" className="btn-secondary btn-sm" onClick={() => { setShowComponentForm(null); setEditingComponent(null); }}>Annuleren</button>
                    </div>
                  </form>
                )}

                {(a.sub_registrations ?? []).length === 0 && showComponentForm !== a.id && (
                  <p className="text-sm text-gray-400 italic">Geen onderdelen.</p>
                )}

                {(a.sub_registrations ?? []).map((comp, ci) => (
                  <div key={comp.id} className="border border-gray-200 rounded-lg">
                    <div className="flex items-center justify-between p-3 bg-gray-50 rounded-t-lg">
                      <div className="flex items-center gap-2">
                        <div className="flex flex-col gap-0.5">
                          <button className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none text-xs" disabled={ci === 0} onClick={() => moveComponent(a.id, a.sub_registrations ?? [], ci, -1)}>▲</button>
                          <button className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none text-xs" disabled={ci === (a.sub_registrations ?? []).length - 1} onClick={() => moveComponent(a.id, a.sub_registrations ?? [], ci, 1)}>▼</button>
                        </div>
                        <span className="font-medium text-sm">{comp.name}</span>
                        {comp.team_name_required && (
                          <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">ploegnaam</span>
                        )}
                      </div>
                      <div className="flex gap-2">
                        {!comp.external_register_url && (
                          <button className="btn-secondary btn-sm text-xs" onClick={() => loadRegistrations(a.id, comp.id)}>Inschrijvingen</button>
                        )}
                        <button className="btn-secondary btn-sm text-xs" onClick={() => {
                          setExpandedComponent(expandedComponent === comp.id ? null : comp.id);
                          setShowProductForm(null);
                        }}>
                          {expandedComponent === comp.id ? "Verberg" : "Producten"}
                        </button>
                        <button className="btn-secondary btn-sm text-xs" onClick={() => startEditComponent(a.id, comp)}>✏️</button>
                        <button className="btn-danger btn-sm text-xs" onClick={() => handleDeleteComponent(a.id, comp.id)}>🗑️</button>
                      </div>
                    </div>

                    {expandedComponent === comp.id && (
                      <div className="p-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-500 font-medium">Producten</span>
                          <button className="btn-secondary btn-sm text-xs" onClick={() => { setShowProductForm(comp.id); setEditingProduct(null); setProductForm(emptyProduct()); }}>
                            + Product
                          </button>
                        </div>

                        {showProductForm === comp.id && (
                          <form onSubmit={(e) => handleProductSubmit(e, a.id, comp.id)} className="bg-blue-50 rounded-lg p-3 space-y-3">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              <div className="sm:col-span-2">
                                <label className="label">Naam *</label>
                                <input className="input" required value={productForm.name}
                                  onChange={(e) => setProductForm((f) => ({ ...f, name: e.target.value }))} />
                              </div>
                              <div className="flex items-center gap-2 col-span-2">
                                <input type="checkbox" id={`free-${comp.id}`} checked={productForm.is_free}
                                  onChange={(e) => setProductForm((f) => ({ ...f, is_free: e.target.checked }))} />
                                <label htmlFor={`free-${comp.id}`}>Gratis</label>
                              </div>
                              {!productForm.is_free && (
                                <>
                                  <div>
                                    <label className="label">Prijs niet-leden (€) *</label>
                                    <input type="number" step="0.01" min="0" className="input" required value={productForm.price}
                                      onChange={(e) => setProductForm((f) => ({ ...f, price: e.target.value }))} />
                                  </div>
                                  <div>
                                    <label className="label">Ledenprijs (€, optioneel)</label>
                                    <input type="number" step="0.01" min="0" className="input" value={productForm.member_price}
                                      onChange={(e) => setProductForm((f) => ({ ...f, member_price: e.target.value }))} />
                                  </div>
                                </>
                              )}
                              <div>
                                <label className="label">Max. deelnemers</label>
                                <input type="number" className="input" value={productForm.max_participants}
                                  onChange={(e) => setProductForm((f) => ({ ...f, max_participants: e.target.value }))} />
                              </div>
                            </div>
                            <div className="flex gap-2">
                              <button type="submit" className="btn-primary btn-sm">Opslaan</button>
                              <button type="button" className="btn-secondary btn-sm" onClick={() => { setShowProductForm(null); setEditingProduct(null); }}>Annuleren</button>
                            </div>
                          </form>
                        )}

                        {comp.products.length === 0 && showProductForm !== comp.id && (
                          <p className="text-xs text-gray-400 italic">Geen producten.</p>
                        )}
                        {comp.products.map((p, pi) => (
                          <div key={p.id} className="flex items-center justify-between text-sm py-1 border-b border-gray-100 last:border-0">
                            <div className="flex items-center gap-2">
                              <div className="flex flex-col gap-0.5">
                                <button className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none text-xs" disabled={pi === 0} onClick={() => moveProduct(a.id, comp.id, comp.products, pi, -1)}>▲</button>
                                <button className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none text-xs" disabled={pi === comp.products.length - 1} onClick={() => moveProduct(a.id, comp.id, comp.products, pi, 1)}>▼</button>
                              </div>
                              <div>
                                <span className="font-medium">{p.name}</span>
                                {p.is_free ? (
                                  <span className="ml-2 text-xs text-green-600">gratis</span>
                                ) : (
                                  <span className="ml-2 text-xs text-gray-500">
                                    €{parseFloat(p.price).toFixed(2)}
                                    {p.member_price ? ` / leden €${parseFloat(p.member_price).toFixed(2)}` : ""}
                                  </span>
                                )}
                                {p.max_participants && <span className="ml-2 text-xs text-gray-400">max {p.max_participants}</span>}
                              </div>
                            </div>
                            <div className="flex gap-1">
                              <button className="btn-secondary btn-sm text-xs" onClick={() => startEditProduct(a.id, comp.id, p)}>✏️</button>
                              <button className="btn-danger btn-sm text-xs" onClick={() => handleDeleteProduct(a.id, comp.id, p.id)}>🗑️</button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
          </div>
        ))}
        {list.length === 0 && <p className="text-gray-500 text-sm">Geen activiteiten.</p>}
      </div>
    </div>
  );
}
