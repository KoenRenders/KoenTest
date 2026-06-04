"use client";
import { useEffect, useState } from "react";
import { getFamilies, getFamily, createMembership } from "@/lib/api";
import type { Family } from "@/lib/types";

export default function AdminLeden() {
  const [families, setFamilies] = useState<Family[]>([]);
  const [selected, setSelected] = useState<Family | null>(null);
  const [year, setYear] = useState(new Date().getFullYear());

  useEffect(() => {
    getFamilies().then((r) => setFamilies(r.data)).catch(() => {});
  }, []);

  async function loadFamily(id: number) {
    const r = await getFamily(id);
    setSelected(r.data);
  }

  async function addMembership(familyId: number) {
    await createMembership(familyId, { year, is_active: true });
    loadFamily(familyId);
  }

  return (
    <div className="flex flex-col md:flex-row gap-6">
      <div className="md:w-64 shrink-0">
        <h1 className="text-2xl font-bold text-blue-800 mb-4">Leden</h1>
        <div className="space-y-2">
          {families.map((f) => (
            <button
              key={f.id}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm border transition-colors ${selected?.id === f.id ? "bg-blue-700 text-white border-blue-700" : "bg-white border-gray-200 hover:bg-gray-50"}`}
              onClick={() => loadFamily(f.id)}
            >
              <div className="font-medium">{f.members.find((m) => m.is_primary)?.last_name || "—"} {f.members.find((m) => m.is_primary)?.first_name || ""}</div>
              <div className={`text-xs ${selected?.id === f.id ? "text-blue-200" : "text-gray-500"}`}>{f.street} {f.house_number}, {f.municipality}</div>
            </button>
          ))}
          {families.length === 0 && <p className="text-sm text-gray-500">Geen gezinnen gevonden.</p>}
        </div>
      </div>

      {selected && (
        <div className="flex-1 min-w-0">
          <div className="card mb-4">
            <h2 className="font-bold text-lg mb-3">Gezin #{selected.id}</h2>
            <p className="text-gray-700">{selected.street} {selected.house_number}{selected.bus_number ? ` bus ${selected.bus_number}` : ""}, {selected.postal_code} {selected.municipality}</p>
          </div>
          <div className="card mb-4">
            <h3 className="font-semibold mb-3">Gezinsleden</h3>
            <div className="space-y-2">
              {selected.members.map((m) => (
                <div key={m.id} className="flex items-start justify-between text-sm">
                  <div>
                    <span className="font-medium">{m.first_name} {m.last_name}</span>
                    {m.is_primary && <span className="ml-2 text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">Hoofdlid</span>}
                    <div className="text-gray-500">{m.email} {m.phone ? `· ${m.phone}` : ""}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <h3 className="font-semibold mb-3">Lidmaatschap toevoegen</h3>
            <div className="flex gap-3 items-end">
              <div>
                <label className="label">Jaar</label>
                <input type="number" className="input w-28" value={year} onChange={(e) => setYear(parseInt(e.target.value))} />
              </div>
              <button className="btn-primary btn-sm" onClick={() => addMembership(selected.id)}>Lid maken</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
