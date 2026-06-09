"use client";
import { useState } from "react";
import { getPublicRegistrations } from "@/lib/api";
import type { Activity, ActivityProduct } from "@/lib/types";

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

function ProductRow({ activityId, product }: { activityId: number; product: ActivityProduct }) {
  const [open, setOpen] = useState(false);
  const [participants, setParticipants] = useState<ParticipantEntry[]>([]);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (!open && participants.length === 0) {
      setLoading(true);
      try {
        const r = await getPublicRegistrations(activityId, product.id);
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

  return (
    <div className="text-sm">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-medium text-gray-700">{product.name}</span>
        {product.is_free ? (
          <span className="text-xs text-green-600">gratis</span>
        ) : (
          <span className="text-xs text-gray-500">
            €{parseFloat(product.price).toFixed(2)}
            {product.member_price && parseFloat(product.member_price) > 0
              ? ` / leden €${parseFloat(product.member_price).toFixed(2)}`
              : ""}
          </span>
        )}
        <button
          onClick={toggle}
          className="text-xs text-blue-600 hover:underline"
        >
          {loading ? "…" : open ? "Verberg" : "Wie doet er mee?"}
        </button>
      </div>
      {open && (
        <div className="mt-1 text-xs text-gray-600 pl-2">
          {participants.length === 0 ? (
            <span className="italic">Nog geen inschrijvingen.</span>
          ) : (
            <>
              <span className="font-medium">{totalCount} deelnemer(s)</span>
              {" — "}
              {participants.map((p, i) => (
                <span key={i}>
                  {p.contact_name}{p.team_name ? ` (${p.team_name})` : ""}{p.quantity > 1 ? ` ×${p.quantity}` : ""}
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
  onRegister?: (activity: Activity) => void;
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
  const canRegister = (a: Activity) =>
    showRegister && onRegister && !past.includes(a.status ?? "") &&
    (a.sub_registrations ?? []).some((c) => c.products.length > 0);

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
                      {activity.max_participants && (
                        <p>👥 {activity.registration_count ?? 0} / {activity.max_participants} deelnemers</p>
                      )}
                    </div>

                    {/* Components and products */}
                    {(activity.sub_registrations ?? []).length > 0 && (
                      <div className="mt-3 space-y-3">
                        {(activity.sub_registrations ?? []).map((comp) => (
                          <div key={comp.id}>
                            <div className="text-sm font-semibold text-gray-800 mb-1">
                              {comp.name}
                              {comp.team_name_required && (
                                <span className="ml-2 text-xs font-normal text-blue-600">(ploegnaam vereist)</span>
                              )}
                              {comp.external_register_url && (
                                <a href={comp.external_register_url} target="_blank" rel="noopener noreferrer"
                                  className="ml-2 text-xs text-blue-600 hover:underline">
                                  Extern inschrijven ↗
                                </a>
                              )}
                            </div>
                            <div className="pl-3 border-l-2 border-blue-100 space-y-1">
                              {comp.products.map((p) => (
                                <ProductRow key={p.id} activityId={activity.id} product={p} />
                              ))}
                              {comp.products.length === 0 && comp.external_registrations_url && (
                                <a href={comp.external_registrations_url} target="_blank" rel="noopener noreferrer"
                                  className="text-xs text-blue-600 hover:underline">
                                  Bekijk inschrijvingen ↗
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {canRegister(activity) && (
                    <button
                      className="btn-primary btn-sm whitespace-nowrap self-start"
                      onClick={() => onRegister!(activity)}
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
