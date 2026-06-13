"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getMemberHousehold,
  getMemberMe,
  updateMemberPerson,
  addMemberPerson,
  removeMemberPerson,
  renewMembership,
} from "@/lib/api";

interface PostalOption { postal_code: string; municipality: string; }

interface PersonData {
  id: number;
  first_name: string;
  last_name: string;
  date_of_birth: string | null;
  gender_code: string | null;
  relation_type: string | null;
  address: {
    id: number;
    street: string;
    house_number: string;
    bus_number: string | null;
    postal_code: string | null;
    municipality: string | null;
    postal_code_id: number;
  } | null;
  email: string | null;
  phone: string | null;
  mobile: string | null;
}

interface Household {
  member_id: number;
  board_member_id: number | null;
  board_member_name: string | null;
  persons: PersonData[];
}

function PostalAutocomplete({
  value,
  onChange,
  postalCodes,
}: {
  value: string;
  onChange: (code: string) => void;
  postalCodes: PostalOption[];
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
              onMouseDown={() => {
                setInput(`${p.postal_code} — ${p.municipality}`);
                onChange(p.postal_code);
                setOpen(false);
              }}
            >
              <span className="font-medium">{p.postal_code}</span> — {p.municipality}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PersonForm({
  initial,
  postalCodes,
  onSave,
  onCancel,
  saving,
  error,
  isNew = false,
}: {
  initial: Partial<PersonData>;
  postalCodes: PostalOption[];
  onSave: (data: Record<string, unknown>) => void;
  onCancel: () => void;
  saving: boolean;
  error: string;
  isNew?: boolean;
}) {
  const [form, setForm] = useState({
    first_name: initial.first_name ?? "",
    last_name: initial.last_name ?? "",
    date_of_birth: initial.date_of_birth ?? "",
    gender_code: initial.gender_code ?? "",
    email: initial.email ?? "",
    phone: initial.phone ?? "",
    mobile: initial.mobile ?? "",
    street: initial.address?.street ?? "",
    house_number: initial.address?.house_number ?? "",
    bus_number: initial.address?.bus_number ?? "",
    postal_code: initial.address?.postal_code ?? "",
  });

  function set(k: string, v: string) { setForm((f) => ({ ...f, [k]: v })); }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    onSave({
      first_name: form.first_name,
      last_name: form.last_name,
      date_of_birth: form.date_of_birth || null,
      gender_code: form.gender_code || null,
      email: form.email || null,
      phone: form.phone || null,
      mobile: form.mobile || null,
      address: {
        street: form.street,
        house_number: form.house_number,
        bus_number: form.bus_number || null,
        postal_code: form.postal_code || null,
      },
      ...(isNew && {
        street: form.street,
        house_number: form.house_number,
        bus_number: form.bus_number || null,
        postal_code: form.postal_code || null,
      }),
    });
  }

  return (
    <form onSubmit={submit} className="space-y-3 mt-3 border-t pt-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Voornaam *</label>
          <input className="input" required value={form.first_name} onChange={(e) => set("first_name", e.target.value)} />
        </div>
        <div>
          <label className="label">Achternaam *</label>
          <input className="input" required value={form.last_name} onChange={(e) => set("last_name", e.target.value)} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Geboortedatum</label>
          <input type="date" className="input" value={form.date_of_birth ?? ""} onChange={(e) => set("date_of_birth", e.target.value)} />
        </div>
        <div>
          <label className="label">Geslacht</label>
          <select className="input" value={form.gender_code} onChange={(e) => set("gender_code", e.target.value)}>
            <option value="">—</option>
            <option value="M">Man</option>
            <option value="V">Vrouw</option>
            <option value="X">Niet-binair</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <div className="col-span-2">
          <label className="label">Straat</label>
          <input className="input" value={form.street} onChange={(e) => set("street", e.target.value)} />
        </div>
        <div>
          <label className="label">Huisnr.</label>
          <input className="input" value={form.house_number} onChange={(e) => set("house_number", e.target.value)} />
        </div>
        <div>
          <label className="label">Bus</label>
          <input className="input" value={form.bus_number ?? ""} onChange={(e) => set("bus_number", e.target.value)} />
        </div>
      </div>
      <div className="grid grid-cols-4 gap-3">
        <div className="col-span-4">
          <label className="label">Postcode</label>
          <PostalAutocomplete
            value={form.postal_code}
            postalCodes={postalCodes}
            onChange={(code) => set("postal_code", code)}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="label">E-mail</label>
          <input type="email" className="input" value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} />
        </div>
        <div>
          <label className="label">Telefoon</label>
          <input type="tel" className="input" value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} />
        </div>
        <div>
          <label className="label">Mobiel</label>
          <input type="tel" className="input" value={form.mobile ?? ""} onChange={(e) => set("mobile", e.target.value)} />
        </div>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Bewaren…" : "Bewaren"}</button>
        <button type="button" className="btn-secondary" onClick={onCancel}>Annuleren</button>
      </div>
    </form>
  );
}

function RelationLabel({ code }: { code: string | null }) {
  const map: Record<string, string> = { HOOFDLID: "Hoofdlid", PARTNER: "Partner", KIND: "Kind" };
  return <span className="text-xs text-gray-500 ml-1">({code ? (map[code] ?? code) : "—"})</span>;
}

export default function MijnGezinPage() {
  const router = useRouter();
  const [household, setHousehold] = useState<Household | null>(null);
  const [postalCodes, setPostalCodes] = useState<PostalOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [addingPerson, setAddingPerson] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [memberEmail, setMemberEmail] = useState("");
  const [membershipValidUntil, setMembershipValidUntil] = useState<string | null>(null);
  const [renewing, setRenewing] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !localStorage.getItem("auth_token")) {
      router.push("/login");
      return;
    }
    Promise.all([getMemberHousehold(), getMemberMe(), fetch("/api/v1/postal-codes").then((r) => r.json())])
      .then(([h, me, pc]) => {
        setHousehold(h.data);
        setMemberEmail(me.data.email);
        setMembershipValidUntil(me.data.membership_valid_until);
        setPostalCodes(pc);
      })
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  async function handleRenew() {
    setRenewing(true);
    try {
      const res = await renewMembership();
      window.location.href = res.data.checkout_url;
    } catch {
      alert("Vernieuwen mislukt. Probeer het later opnieuw.");
      setRenewing(false);
    }
  }

  async function savePerson(personId: number, data: Record<string, unknown>) {
    setSaving(true);
    setSaveError("");
    try {
      const res = await updateMemberPerson(personId, data);
      setHousehold((h) => h ? {
        ...h,
        persons: h.persons.map((p) => p.id === personId ? res.data : p),
      } : h);
      setEditingId(null);
    } catch {
      setSaveError("Bewaren mislukt. Probeer opnieuw.");
    } finally {
      setSaving(false);
    }
  }

  async function addPerson(data: Record<string, unknown>) {
    setSaving(true);
    setSaveError("");
    try {
      const res = await addMemberPerson(data);
      setHousehold((h) => h ? { ...h, persons: [...h.persons, res.data] } : h);
      setAddingPerson(false);
    } catch {
      setSaveError("Toevoegen mislukt. Probeer opnieuw.");
    } finally {
      setSaving(false);
    }
  }

  async function removePerson(personId: number) {
    if (!confirm("Weet je zeker dat je deze persoon uit het gezin wil verwijderen?")) return;
    setRemovingId(personId);
    try {
      await removeMemberPerson(personId);
      setHousehold((h) => h ? { ...h, persons: h.persons.filter((p) => p.id !== personId) } : h);
    } catch {
      alert("Verwijderen mislukt. Probeer opnieuw.");
    } finally {
      setRemovingId(null);
    }
  }

  if (loading) return <p className="text-gray-500 mt-8">Laden…</p>;
  if (!household) return null;

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold text-blue-800 mb-2">Mijn gezin</h1>
      <p className="text-gray-600 mb-6 text-sm">
        Ingelogd als <strong>{memberEmail}</strong>.{" "}
        {household.board_member_name && (
          <span>Verantwoordelijk lid: <strong>{household.board_member_name}</strong> (alleen bestuur kan dit wijzigen).</span>
        )}
      </p>

      <div className={`card mb-6 ${membershipValidUntil ? "" : "border-l-4 border-amber-400"}`}>
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="font-semibold text-gray-900">Lidmaatschap</h2>
            {membershipValidUntil ? (
              <p className="text-sm text-green-700 mt-0.5">
                Actief — geldig tot {new Date(membershipValidUntil).toLocaleDateString("nl-BE")}.
              </p>
            ) : (
              <p className="text-sm text-amber-700 mt-0.5">
                Je hebt op dit moment geen geldig lidmaatschap.
              </p>
            )}
          </div>
          {!membershipValidUntil && (
            <button className="btn-primary" onClick={handleRenew} disabled={renewing}>
              {renewing ? "Bezig…" : "Lidmaatschap vernieuwen"}
            </button>
          )}
        </div>
      </div>

      <div className="space-y-4">
        {household.persons.map((p) => (
          <div key={p.id} className="card">
            <div className="flex items-start justify-between">
              <div>
                <span className="font-semibold text-gray-900">
                  {p.first_name} {p.last_name}
                </span>
                <RelationLabel code={p.relation_type} />
                {p.date_of_birth && (
                  <p className="text-sm text-gray-500 mt-0.5">° {new Date(p.date_of_birth).toLocaleDateString("nl-BE")}</p>
                )}
                {p.address && (
                  <p className="text-sm text-gray-600 mt-0.5">
                    {p.address.street} {p.address.house_number}{p.address.bus_number ? ` bus ${p.address.bus_number}` : ""}, {p.address.postal_code} {p.address.municipality}
                  </p>
                )}
                <div className="text-sm text-gray-500 mt-0.5 space-x-3">
                  {p.email && <span>✉ {p.email}</span>}
                  {p.phone && <span>☎ {p.phone}</span>}
                  {p.mobile && <span>📱 {p.mobile}</span>}
                </div>
              </div>
              <div className="flex gap-2 ml-4 shrink-0">
                <button
                  className="text-sm text-blue-700 hover:underline"
                  onClick={() => { setEditingId(editingId === p.id ? null : p.id); setSaveError(""); }}
                >
                  {editingId === p.id ? "Sluiten" : "Bewerken"}
                </button>
                {p.id !== household.persons.find((x) => x.relation_type === "HOOFDLID")?.id && (
                  <button
                    className="text-sm text-red-600 hover:underline"
                    onClick={() => removePerson(p.id)}
                    disabled={removingId === p.id}
                  >
                    {removingId === p.id ? "…" : "Verwijderen"}
                  </button>
                )}
              </div>
            </div>

            {editingId === p.id && (
              <PersonForm
                initial={p}
                postalCodes={postalCodes}
                onSave={(data) => savePerson(p.id, data)}
                onCancel={() => setEditingId(null)}
                saving={saving}
                error={saveError}
              />
            )}
          </div>
        ))}
      </div>

      {addingPerson ? (
        <div className="card mt-4">
          <h3 className="font-semibold text-gray-900 mb-1">Persoon toevoegen</h3>
          <PersonForm
            initial={{}}
            postalCodes={postalCodes}
            onSave={addPerson}
            onCancel={() => setAddingPerson(false)}
            saving={saving}
            error={saveError}
            isNew
          />
        </div>
      ) : (
        <button className="btn-secondary mt-4" onClick={() => { setAddingPerson(true); setSaveError(""); }}>
          + Persoon toevoegen
        </button>
      )}
    </div>
  );
}
