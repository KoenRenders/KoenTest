"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getMemberHousehold,
  getMemberMe,
  updateMemberPerson,
  addMemberPerson,
  removeMemberPerson,
  renewMembership,
  getGenderCodes,
} from "@/lib/api";
import { type PersonInput, type AddressInput, type PostalOption } from "@/components/household/types";
import PersonFields from "@/components/household/PersonFields";
import AddressFields from "@/components/household/AddressFields";
import { usePostalCodes } from "@/components/household/usePostalCodes";

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

function PersonForm({
  initial,
  postalCodes,
  genderCodes,
  isHoofdlid,
  onSave,
  onCancel,
  saving,
  error,
}: {
  initial: Partial<PersonData>;
  postalCodes: PostalOption[];
  genderCodes: { code: string; value: string }[];
  isHoofdlid: boolean;
  onSave: (data: Record<string, unknown>) => void;
  onCancel: () => void;
  saving: boolean;
  error: string;
}) {
  const [person, setPerson] = useState<PersonInput>({
    first_name: initial.first_name ?? "",
    last_name: initial.last_name ?? "",
    date_of_birth: initial.date_of_birth ?? "",
    gender_code: initial.gender_code ?? "",
    email: initial.email ?? "",
    phone: initial.phone ?? "",
    mobile: initial.mobile ?? "",
    relation_type: initial.relation_type ?? "",
  });
  const [address, setAddress] = useState<AddressInput>({
    street: initial.address?.street ?? "",
    house_number: initial.address?.house_number ?? "",
    bus_number: initial.address?.bus_number ?? "",
    postal_code: initial.address?.postal_code ?? "",
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload: Record<string, unknown> = {
      first_name: person.first_name,
      last_name: person.last_name,
      date_of_birth: person.date_of_birth || null,
      gender_code: person.gender_code || null,
      email: person.email || null,
      phone: person.phone || null,
      mobile: person.mobile || null,
    };
    // Adres hoort enkel bij het hoofdlid (= gezinsadres). #125
    if (isHoofdlid) {
      payload.address = {
        street: address.street,
        house_number: address.house_number,
        bus_number: address.bus_number || null,
        postal_code: address.postal_code || null,
      };
    }
    onSave(payload);
  }

  return (
    <form onSubmit={submit} className="space-y-3 mt-3 border-t pt-3">
      <PersonFields
        person={person}
        onChange={(patch) => setPerson((p) => ({ ...p, ...patch }))}
        genderCodes={genderCodes}
        requireContact={isHoofdlid}
      />

      {isHoofdlid && (
        <div>
          <label className="label">Adres</label>
          <AddressFields address={address} onChange={(patch) => setAddress((a) => ({ ...a, ...patch }))} postalCodes={postalCodes} />
        </div>
      )}

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
  const postalCodes = usePostalCodes();
  const [genderCodes, setGenderCodes] = useState<{ code: string; value: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [addingPerson, setAddingPerson] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [memberEmail, setMemberEmail] = useState("");
  const [membershipValidUntil, setMembershipValidUntil] = useState<string | null>(null);
  const [renewalAvailable, setRenewalAvailable] = useState(false);
  const [renewing, setRenewing] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !localStorage.getItem("auth_token")) {
      router.push("/login");
      return;
    }
    getGenderCodes().then((r) => setGenderCodes(r.data)).catch(() => {});
    Promise.all([getMemberHousehold(), getMemberMe()])
      .then(([h, me]) => {
        setHousehold(h.data);
        setMemberEmail(me.data.email);
        setMembershipValidUntil(me.data.membership_valid_until);
        setRenewalAvailable(me.data.renewal_available);
      })
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  const hoofdlidId = household?.persons.find((x) => x.relation_type === "HOOFDLID")?.id ?? null;

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
          {renewalAvailable && (
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
                <div className="text-sm text-gray-500 mt-0.5">
                  <div className="flex gap-3 flex-wrap">
                    {p.email && <span>✉ {p.email}</span>}
                    {p.mobile && <span>📱 {p.mobile}</span>}
                  </div>
                  {p.phone && <div>☎ {p.phone}</div>}
                </div>
              </div>
              <div className="flex gap-2 ml-4 shrink-0">
                <button
                  className="text-sm text-blue-700 hover:underline"
                  onClick={() => { setEditingId(editingId === p.id ? null : p.id); setSaveError(""); }}
                >
                  {editingId === p.id ? "Sluiten" : "Bewerken"}
                </button>
                {p.id !== hoofdlidId && (
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
                genderCodes={genderCodes}
                isHoofdlid={p.id === hoofdlidId}
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
            genderCodes={genderCodes}
            isHoofdlid={false}
            onSave={addPerson}
            onCancel={() => setAddingPerson(false)}
            saving={saving}
            error={saveError}
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
