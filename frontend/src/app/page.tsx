"use client";
import { useEffect, useState } from "react";
import { getActivities, getBlock, getAuthMe } from "@/lib/api";
import ActivityList from "@/components/ActivityList";
import RegistrationForm from "@/components/RegistrationForm";
import IdeaBox from "@/components/IdeaBox";
import FamilyRegistrationForm from "@/components/FamilyRegistrationForm";
import { sanitizeCmsHtml } from "@/lib/sanitize";
import type { Activity, ActivityComponent, CmsPage } from "@/lib/types";

export default function HomePage() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<{ activity: Activity; component: ActivityComponent } | null>(null);
  const [registered, setRegistered] = useState(false);
  const [showRegForm, setShowRegForm] = useState(false);
  const [showContact, setShowContact] = useState(false);
  const [introPage, setIntroPage] = useState<CmsPage | null>(null);
  const [isMember, setIsMember] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem("auth_token")) {
      getAuthMe().then((r) => { if (r.data.is_member) setIsMember(true); }).catch(() => {});
    }
    getActivities()
      .then((r) => setActivities(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
    getBlock("home-intro").then((r) => setIntroPage(r.data)).catch(() => {});
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
      <section className="py-8">
        {introPage?.content && (
          <div
            className="cms-content mb-6 text-gray-700"
            dangerouslySetInnerHTML={{ __html: sanitizeCmsHtml(introPage.content) }}
          />
        )}
        <div className="flex flex-wrap gap-3">
          <button className="btn-primary" onClick={() => {
            if (isMember) { window.location.href = "/leden/gezin"; return; }
            setShowRegForm((s) => !s); setShowContact(false);
          }}>
            {showRegForm ? "Sluit registratie" : "Word lid"}
          </button>
          <button className="btn-primary" onClick={() => { setShowContact((s) => !s); setShowRegForm(false); }}>
            {showContact ? "Sluit" : "Contacteer ons"}
          </button>
        </div>
      </section>

      {/* Lid worden */}
      {showRegForm && (
        <section className="card">
          <h2 className="text-2xl font-bold mb-6 text-blue-800">Lid worden</h2>
          <FamilyRegistrationForm />
        </section>
      )}

      {/* Contacteer ons */}
      {showContact && (
        <section>
          <IdeaBox />
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
          <ActivityList activities={activities} onRegister={(a, c) => setSelected({ activity: a, component: c })} showRegister yearsAscending />
        )}
      </section>

      {/* Registratie modal */}
      {selected && (
        <RegistrationForm
          activity={selected.activity}
          component={selected.component}
          onClose={() => setSelected(null)}
          onSuccess={handleRegistered}
        />
      )}
    </div>
  );
}
