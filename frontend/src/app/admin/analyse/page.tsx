"use client";
import { useEffect, useState } from "react";
import { getBusinessEventStats, type BusinessEventStats } from "@/lib/api";
import { parseApiError } from "@/lib/errors";

// Vriendelijke labels per event-type. Onbekende types vallen terug op hun code.
const LABELS: Record<string, string> = {
  lid_worden_voltooid: "Lid worden – aangevraagd",
  inschrijving_voltooid: "Inschrijvingen (activiteiten)",
  hernieuwing_gestart: "Hernieuwing – gestart",
  betaling_succes: "Betaling – geslaagd",
  betaling_geannuleerd: "Betaling – geannuleerd",
  betaling_terugbetaling: "Terugbetaling",
};

function eur(n: number) {
  return `€ ${n.toFixed(2)}`;
}

export default function AdminAnalysePage() {
  const [stats, setStats] = useState<BusinessEventStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBusinessEventStats()
      .then((res) => setStats(res.data))
      .catch((err) => setError(parseApiError(err, "Kon het rapport niet laden.")));
  }, []);

  if (error) return <div className="card p-4 text-red-600">{error}</div>;
  if (!stats) return <div className="card p-4">Laden…</div>;

  const types = Array.from(
    new Set([...Object.keys(stats.totals), ...Object.keys(stats.totals_30d)])
  ).sort();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-blue-800">Analyse</h1>
      <p className="text-sm text-gray-600">
        First-party business-events op de kernflows (registratie, betaling,
        hernieuwing). Geen persoonsgegevens — enkel geaggregeerde cijfers.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="rounded-xl p-5 bg-green-50 text-green-800">
          <div className="text-3xl font-extrabold">{eur(stats.revenue_paid_eur)}</div>
          <div className="text-sm font-medium mt-1">Netto-omzet — alle betaalwijzen, na terugbetalingen (totaal)</div>
        </div>
        <div className="rounded-xl p-5 bg-emerald-50 text-emerald-800">
          <div className="text-3xl font-extrabold">{eur(stats.revenue_paid_eur_30d)}</div>
          <div className="text-sm font-medium mt-1">
            Netto-omzet laatste {stats.period_days} dagen
          </div>
        </div>
      </div>

      <div className="card p-4">
        <h2 className="font-bold text-blue-800 mb-3">Gebeurtenissen per type</h2>
        {types.length === 0 ? (
          <p className="text-gray-500">Nog geen gebeurtenissen geregistreerd.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-600 border-b border-gray-200">
                <th className="py-2">Type</th>
                <th className="py-2 text-right">Totaal</th>
                <th className="py-2 text-right">Laatste {stats.period_days} d.</th>
              </tr>
            </thead>
            <tbody>
              {types.map((t) => (
                <tr key={t} className="border-b border-gray-100">
                  <td className="py-2 font-medium text-gray-900">{LABELS[t] ?? t}</td>
                  <td className="py-2 text-right">{stats.totals[t] ?? 0}</td>
                  <td className="py-2 text-right">{stats.totals_30d[t] ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
