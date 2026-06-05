"use client";
import { useEffect, useState } from "react";
import { getActivities } from "@/lib/api";
import ActivityList from "@/components/ActivityList";
import RegistrationForm from "@/components/RegistrationForm";
import IdeaBox from "@/components/IdeaBox";
import FamilyRegistrationForm from "@/components/FamilyRegistrationForm";
import type { Activity } from "@/lib/types";

export default function HomePage() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Activity | null>(null);
  const [registered, setRegistered] = useState(false);
  const [showRegForm, setShowRegForm] = useState(false);

  useEffect(() => {
    getActivities()
      .then((r) => setActivities(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function handleRegistered() {
    setSelected(null);
    setRegistered(true);
    setTimeout(() => setRegistered(false), 5000);
    getActivities().then((r) => setActivities(r.data)).catch(() => {});
  }

  return (
    <div className="space-y-12">
      {/* Hero */}
      <section className="text-center py-8">
        <h1 className="text-4xl font-extrabold text-blue-800 mb-3">Raak Millegem</h1>
        <p className="text-gray-600 text-lg mb-6">
          KWB-afdeling Millegem — activiteiten, nieuws en meer voor onze leden.
        </p>
        <button className="btn-primary" onClick={() => setShowRegForm((s) => !s)}>
          {showRegForm ? "Sluit registratie" : "Word lid"}
        </button>
      </section>

      {/* Lid worden */}
      {showRegForm && (
        <section className="card">
          <h2 className="text-2xl font-bold mb-6 text-blue-800">Lid worden</h2>
          <FamilyRegistrationForm />
        </section>
      )}

      {/* Activiteiten */}
      <section>
        <h2 className="text-2xl font-bold mb-6 text-blue-800">Activiteiten</h2>
        {registered && (
          <div className="mb-4 bg-green-50 border border-green-200 rounded-lg p-4 text-green-800">
            ✅ Je inschrijving is ontvangen!
          </div>
        )}
        {loading ? (
          <p className="text-gray-500">Activiteiten laden…</p>
        ) : (
          <ActivityList activities={activities} onRegister={setSelected} showRegister={false} yearsAscending />
        )}
      </section>

      {/* Ideeënbus */}
      <IdeaBox />

      {/* Registratie modal */}
      {selected && (
        <RegistrationForm
          activity={selected}
          onClose={() => setSelected(null)}
          onSuccess={handleRegistered}
        />
      )}
    </div>
  );
}
