"use client";
import Link from "next/link";
import type { Activity } from "@/lib/types";

function StatusBadge({ status }: { status?: string }) {
  if (status === "Vol") return <span className="status-vol">Vol</span>;
  if (status === "Wachtlijst") return <span className="status-waitlist">Wachtlijst</span>;
  return <span className="status-open">Open</span>;
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString("nl-BE", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
}

function formatTime(t?: string) {
  if (!t) return null;
  return t.substring(0, 5);
}

export default function ActivityList({
  activities,
  onRegister,
  showRegister = true,
  yearsAscending = false,
}: {
  activities: Activity[];
  onRegister?: (activity: Activity) => void;
  showRegister?: boolean;
  yearsAscending?: boolean;
}) {
  if (activities.length === 0) {
    return <p className="text-gray-500 italic">Geen activiteiten gevonden.</p>;
  }

  // Group by year
  const byYear = activities.reduce<Record<number, Activity[]>>((acc, a) => {
    const year = new Date(a.date).getFullYear();
    (acc[year] = acc[year] || []).push(a);
    return acc;
  }, {});

  const years = Object.keys(byYear)
    .map(Number)
    .sort((a, b) => yearsAscending ? a - b : b - a);

  return (
    <div className="space-y-10">
      {years.map((year) => (
        <div key={year}>
          <h3 className="text-lg font-bold text-blue-800 mb-4 border-b border-blue-200 pb-2">{year}</h3>
          <div className="space-y-4">
            {byYear[year].map((activity) => (
              <div key={activity.id} className="card">
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 flex-wrap">
                      {activity.poster_url ? (
                        <a href={activity.poster_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-blue-700 hover:underline text-lg">
                          {activity.name}
                        </a>
                      ) : (
                        <span className="font-semibold text-gray-900 text-lg">{activity.name}</span>
                      )}
                      <StatusBadge status={activity.status} />
                    </div>
                    <div className="mt-2 text-gray-600 space-y-0.5 text-sm">
                      <p>📅 {formatDate(activity.date)}{formatTime(activity.time) ? ` om ${formatTime(activity.time)}` : ""}</p>
                      {activity.location && <p>📍 {activity.location}</p>}
                      {activity.max_participants && (
                        <p>👥 {activity.registration_count ?? 0} / {activity.max_participants} deelnemers</p>
                      )}
                      {parseFloat(activity.price) > 0 && (
                        <p>💶 €{parseFloat(activity.price).toFixed(2)}
                          {activity.member_price ? ` (leden: €${parseFloat(activity.member_price).toFixed(2)})` : ""}
                        </p>
                      )}
                    </div>
                  </div>
                  {showRegister && onRegister && (
                    <button
                      className="btn-primary btn-sm whitespace-nowrap self-start"
                      onClick={() => onRegister(activity)}
                      disabled={activity.status === "Vol"}
                    >
                      {activity.status === "Vol" ? "Vol" : "Inschrijven"}
                    </button>
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
