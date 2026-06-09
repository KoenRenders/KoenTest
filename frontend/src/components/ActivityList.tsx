"use client";
import { useState } from "react";
import { getPublicRegistrations } from "@/lib/api";
import type { Activity, ActivityComponent } from "@/lib/types";

function StatusBadge({ status }: { status?: string }) {
  if (status === "Vol") return <span className="status-vol">Vol</span>;
  if (status === "Wachtlijst") return <span className="status-waitlist">Wachtlijst</span>;
  if (status === "Voorbij") return <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-500">Voorbij</span>;
  if (status === "Geannuleerd") return <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-600">Geannuleerd</span>;
  return <span className="status-open">Open</span>;
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString("nl-BE", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
}

function formatTime(t?: string) {
  if (!t) return null;
  return t.substring(0, 5);
}

interface ParticipantEntry {
  contact_name: string;
  quantity: number;
  team_name?: string;
}

function ComponentRow({
  activityId,
  component,
  canRegister,
  onRegister,
  activityStatus,
}: {
  activityId: number;
  component: ActivityComponent;
  canRegister: boolean;
  onRegister?: (component: ActivityComponent) => void;
  activityStatus?: string;
}) {
  const [open, setOpen] = useState(false);
  const [participants, setParticipants] = useState<ParticipantEntry[]>([]);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (!open && participants.length === 0) {
      setLoading(true);
      try {
        const r = await getPublicRegistrations(activityId, component.id);
        setParticipants(r.data);
      } catch {
        setParticipants([]);
      } finally {
        setLoading(false);
      }
    }
    setOpen((o) => !o);
  }

  const totalCount = participants.reduce((sum, p) => sum + p.quantity, 0);
  const hasProducts = component.products.length > 0;

  return (
    <div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold text-gray-800">{component.name}</span>
        {component.external_register_url ? (
          <a href={component.external_register_url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-blue-600 border border-blue-200 rounded px-2 py-0.5 hover:bg-blue-50">
            Inschrijven ↗
          </a>
        ) : canRegister && onRegister ? (
          <button
            className="text-xs text-blue-600 border border-blue-200 rounded px-2 py-0.5 hover:bg-blue-50 disabled:opacity-40"
            onClick={() => onRegister(component)}
            disabled={activityStatus === "Vol"}
          >
            {activityStatus === "Vol" ? "Vol" : "Inschrijven"}
          </button>
        ) : null}
        {component.external_registrations_url ? (
          <a href={component.external_registrations_url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-blue-600 border border-blue-200 rounded px-2 py-0.5 hover:bg-blue-50">
            Inschrijvingen ↗
          </a>
        ) : !component.external_register_url ? (
          <button onClick={toggle} className="text-xs text-blue-600 border border-blue-200 rounded px-2 py-0.5 hover:bg-blue-50">
            {loading ? "…" : open ? "Verberg" : "Wie doet er mee?"}
          </button>
        ) : null}
      </div>


      {/* Participant list */}
      {open && (
        <div className="mt-1 text-xs text-gray-600 pl-2">
          {participants.length === 0 ? (
            <span className="italic">Nog geen inschrijvingen.</span>
          ) : (
            <>
              <span className="font-medium">{totalCount} ingeschreven</span>
              {" — "}
              {participants.map((p, i) => (
                <span key={i}>
                  {p.team_name || p.contact_name}
                  {i < participants.length - 1 ? " · " : ""}
                </span>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function ActivityList({
  activities,
  onRegister,
  showRegister = true,
  yearsAscending = false,
}: {
  activities: Activity[];
  onRegister?: (activity: Activity, component: ActivityComponent) => void;
  showRegister?: boolean;
  yearsAscending?: boolean;
}) {
  if (activities.length === 0) {
    return <p className="text-gray-500 italic">Geen activiteiten gevonden.</p>;
  }

  const byYear = activities.reduce<Record<number, Activity[]>>((acc, a) => {
    const year = new Date(a.date).getFullYear();
    (acc[year] = acc[year] || []).push(a);
    return acc;
  }, {});

  const years = Object.keys(byYear)
    .map(Number)
    .sort((a, b) => yearsAscending ? a - b : b - a);

  const past = ["Voorbij", "Geannuleerd"];

  return (
    <div className="space-y-10">
      {years.map((year) => (
        <div key={year}>
          <h3 className="text-lg font-bold text-blue-800 mb-4 border-b border-blue-200 pb-2">{year}</h3>
          <div className="space-y-4">
            {byYear[year].map((activity) => (
              <div key={activity.id} className="card">
                <div className="flex-1">
                  <div className="flex items-center gap-3 flex-wrap">
                    {activity.poster_url ? (
                      <a href={activity.poster_url} target="_blank" rel="noopener noreferrer"
                        className="font-semibold text-blue-700 hover:underline text-lg">
                        {activity.name}
                      </a>
                    ) : (
                      <span className="font-semibold text-gray-900 text-lg">{activity.name}</span>
                    )}
                    <StatusBadge status={activity.status} />
                  </div>
                  <div className="mt-2 text-gray-600 space-y-0.5 text-sm">
                    <p>📅 {formatDate(activity.date)}{activity.date_end && activity.date_end !== activity.date ? ` – ${formatDate(activity.date_end)}` : ""}{formatTime(activity.time) ? ` om ${formatTime(activity.time)}` : ""}</p>
                    {activity.location && <p>📍 {activity.location}</p>}
                  </div>

                  {/* Components */}
                  {(activity.sub_registrations ?? []).length > 0 && (
                    <div className="mt-3 space-y-3">
                      {(activity.sub_registrations ?? []).map((comp) => (
                        <ComponentRow
                          key={comp.id}
                          activityId={activity.id}
                          component={comp}
                          canRegister={showRegister && !past.includes(activity.status ?? "")}
                          onRegister={onRegister ? (c) => onRegister(activity, c) : undefined}
                          activityStatus={activity.status}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
