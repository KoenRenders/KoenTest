"use client";
import type { Activity } from "@/lib/types";

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
                      <p>📅 {formatDate(activity.date)}{activity.date_end && activity.date_end !== activity.date ? ` – ${formatDate(activity.date_end)}` : ""}{formatTime(activity.time) ? ` om ${formatTime(activity.time)}` : ""}</p>
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
                    {activity.sub_registrations && activity.sub_registrations.length > 0 && (
                      activity.sub_registrations.length === 1 ? null : (
                      <div className="mt-3 space-y-2">
                        {activity.sub_registrations.map((sub) => (
                          <div key={sub.id} className="flex items-center gap-2 flex-wrap text-sm pl-3 border-l-2 border-blue-100">
                            <span className="text-gray-700 font-medium">{sub.name}</span>
                            {sub.info_url && (
                              <a href={sub.info_url} target="_blank" rel="noopener noreferrer"
                                className="text-xs text-gray-500 hover:text-blue-600 underline">
                                reglement ↗
                              </a>
                            )}
                            {sub.external_register_url && (
                              <a href={sub.external_register_url} target="_blank" rel="noopener noreferrer"
                                className="px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200">
                                Inschrijven ↗
                              </a>
                            )}
                            {sub.external_registrations_url && (
                              <a href={sub.external_registrations_url} target="_blank" rel="noopener noreferrer"
                                className="px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200">
                                Inschrijvingen ↗
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                      )
                    )}
                  </div>
                  {activity.sub_registrations?.length === 1 && (() => {
                    const sub = activity.sub_registrations![0];
                    return (
                      <div className="flex gap-2 self-start flex-wrap">
                        {sub.info_url && (
                          <a href={sub.info_url} target="_blank" rel="noopener noreferrer"
                            className="text-xs text-gray-500 hover:text-blue-600 underline self-center">
                            reglement ↗
                          </a>
                        )}
                        {sub.external_register_url && (
                          <a href={sub.external_register_url} target="_blank" rel="noopener noreferrer"
                            className="px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 whitespace-nowrap">
                            Inschrijven ↗
                          </a>
                        )}
                        {sub.external_registrations_url && (
                          <a href={sub.external_registrations_url} target="_blank" rel="noopener noreferrer"
                            className="px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 whitespace-nowrap">
                            Inschrijvingen ↗
                          </a>
                        )}
                      </div>
                    );
                  })()}
                  {showRegister && onRegister && !activity.sub_registrations?.length && (
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
