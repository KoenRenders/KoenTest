"use client";
import { useState } from "react";
import { getPublicRegistrations } from "@/lib/api";
import type { Activity, SubRegistration } from "@/lib/types";
import { isPositivePrice, formatPrice } from "@/lib/money";

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

const pillBtn = "px-2 py-0.5 rounded text-xs font-medium border whitespace-nowrap";
const pillOutline = `${pillBtn} bg-white text-blue-600 hover:bg-blue-50 border-blue-200`;
const pillPrimary = `${pillBtn} bg-blue-50 text-blue-700 hover:bg-blue-100 border-blue-200`;

interface RegState { names: string[]; total: number; }

function ProductRow({
  activity, product, compact = false,
}: {
  activity: Activity;
  product: SubRegistration;
  compact?: boolean;
}) {
  const [regs, setRegs] = useState<RegState | null>(null);
  const [regsOpen, setRegsOpen] = useState(false);
  const [regsLoading, setRegsLoading] = useState(false);

  async function toggleRegs() {
    if (regsOpen) { setRegsOpen(false); return; }
    setRegsOpen(true);
    if (regs !== null) return;
    setRegsLoading(true);
    try {
      const res = await getPublicRegistrations(activity.id, product.id);
      setRegs({ names: res.data.names, total: res.data.total_participants });
    } catch {
      setRegs({ names: [], total: 0 });
    } finally {
      setRegsLoading(false);
    }
  }

  const rowClass = compact
    ? "flex items-center gap-2 flex-wrap text-sm"
    : "flex items-center gap-2 flex-wrap text-sm pl-3 border-l-2 border-blue-100";

  return (
    <div>
      <div className={rowClass}>
        {!compact && <span className="text-gray-700 font-medium">{product.name}</span>}
        {!compact && !product.is_free && (
          <span className="text-xs text-gray-500">
            {formatPrice(product.price)}
            {isPositivePrice(product.member_price) ? ` / leden ${formatPrice(product.member_price!)}` : ""}
          </span>
        )}
        {product.external_register_url && (
          <a href={product.external_register_url} target="_blank" rel="noopener noreferrer" className={pillPrimary}>
            Inschrijven ↗
          </a>
        )}
        {product.info_url && (
          <a href={product.info_url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-gray-500 hover:text-blue-600 underline">
            reglement ↗
          </a>
        )}
        {!product.external_register_url && (
          <button onClick={toggleRegs} className={pillOutline}>
            {regsOpen ? "Verberg" : regs !== null ? `Wie doet er mee? (${regs.total})` : "Wie doet er mee?"}
          </button>
        )}
        {!product.external_register_url && product.external_registrations_url && (
          <a href={product.external_registrations_url} target="_blank" rel="noopener noreferrer" className={pillOutline}>
            Inschrijvingen ↗
          </a>
        )}
      </div>
      {regsOpen && (
        <div className="mt-1 ml-3 pl-3 border-l border-blue-100 text-xs text-gray-600">
          {regsLoading && <p className="italic">Laden…</p>}
          {!regsLoading && regs && regs.names.length === 0 && (
            <p className="italic text-gray-400">Nog geen inschrijvingen.</p>
          )}
          {!regsLoading && regs && regs.names.length > 0 && (
            <>
              <p className="font-medium text-gray-500">{regs.total} deelnemer{regs.total !== 1 ? "s" : ""}</p>
              <p>{regs.names.join(" · ")}</p>
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
  onSubRegister,
  showRegister = true,
  yearsAscending = false,
}: {
  activities: Activity[];
  onRegister?: (activity: Activity) => void;
  onSubRegister?: (activity: Activity, sub: SubRegistration) => void;
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

  const years = Object.keys(byYear).map(Number).sort((a, b) => yearsAscending ? a - b : b - a);

  return (
    <div className="space-y-10">
      {years.map((year) => (
        <div key={year}>
          <h3 className="text-lg font-bold text-blue-800 mb-4 border-b border-blue-200 pb-2">{year}</h3>
          <div className="space-y-4">
            {byYear[year].map((activity) => {
              const allProducts = (activity.sub_registrations ?? []);
              const internalProducts = allProducts.filter((s) => !s.external_register_url);
              const hasInternalForm = internalProducts.length > 0;
              const canRegister = showRegister && hasInternalForm && onRegister
                && activity.status !== "Voorbij" && activity.status !== "Geannuleerd";

              return (
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

                      {allProducts.length > 1 && (
                        <div className="mt-3 space-y-2">
                          {allProducts.map((p) => (
                            <ProductRow key={p.id} activity={activity} product={p} />
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col gap-2 self-start items-end">
                      {allProducts.length === 1 && (
                        <ProductRow activity={activity} product={allProducts[0]} compact />
                      )}
                      {canRegister && allProducts.length !== 1 && (
                        <button
                          className="btn-primary btn-sm whitespace-nowrap"
                          onClick={() => onRegister!(activity)}
                          disabled={activity.status === "Vol"}
                        >
                          {activity.status === "Vol" ? "Vol" : "Inschrijven"}
                        </button>
                      )}
                      {canRegister && allProducts.length === 1 && !allProducts[0].external_register_url && (
                        <button
                          className="btn-primary btn-sm whitespace-nowrap"
                          onClick={() => onRegister!(activity)}
                          disabled={activity.status === "Vol"}
                        >
                          {activity.status === "Vol" ? "Vol" : "Inschrijven"}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
