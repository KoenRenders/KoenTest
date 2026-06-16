"use client";
import { useEffect, useState } from "react";
import { getSystemInfo, type SystemInfo } from "@/lib/api";
import { parseApiError } from "@/lib/errors";

// Analytics-config is client-side beschikbaar (NEXT_PUBLIC_*). Het Website ID is
// geen secret (staat in de paginabron). Dashboard-URL = de tracker-src zonder /script.js.
const UMAMI_SRC = process.env.NEXT_PUBLIC_UMAMI_SRC || "";
const UMAMI_WEBSITE_ID = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID || "";
const UMAMI_DASHBOARD = UMAMI_SRC ? UMAMI_SRC.replace(/\/script\.js$/, "/") : "";
const UMAMI_CONFIGURED = Boolean(UMAMI_SRC && UMAMI_WEBSITE_ID);

function Section({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="card p-4">
      <h2 className="font-bold text-blue-800 mb-3">{title}</h2>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 border-b border-gray-100 py-1">
            <dt className="text-gray-600">{k}</dt>
            <dd className="font-medium text-gray-900 text-right break-all">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function AdminInfoPage() {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSystemInfo()
      .then((res) => setInfo(res.data))
      .catch((err) => setError(parseApiError(err, "Kon systeeminfo niet laden.")));
  }, []);

  if (error) return <div className="card p-4 text-red-600">{error}</div>;
  if (!info) return <div className="card p-4">Laden…</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-blue-800">Systeeminfo</h1>

      <Section
        title="Versie & omgeving"
        rows={[
          ["Versie", info.version],
          ["Commit", info.commit],
          ["Omgeving", info.environment],
          ["Servertijd", info.server_time],
          ["Tijdzone", info.timezone],
        ]}
      />

      <Section
        title="Diagnostische vlaggen"
        rows={[
          ["Logniveau", info.flags.log_level],
          ["Debug", info.flags.debug ? "aan" : "uit"],
          ["SQL-echo", info.flags.sql_echo ? "aan" : "uit"],
        ]}
      />

      <Section
        title="Limieten"
        rows={[
          ["Max. aantal per item", String(info.limits.max_item_quantity)],
          ["Max. inschrijvingen per e-mail", String(info.limits.max_registrations_per_email)],
        ]}
      />

      <Section
        title="Lidmaatschap"
        rows={[
          ["Prijs volledig", `€ ${info.membership.price_full}`],
          ["Prijs half", `€ ${info.membership.price_half}`],
          ["Halfprijs van", info.membership.half_price_start_md],
          ["Halfprijs tot", info.membership.half_price_end_md],
          ["Volgend jaar vanaf", info.membership.next_year_from_md],
          ["Hernieuwen vanaf", info.membership.renewal_start_md ?? "—"],
        ]}
      />

      <Section
        title="URLs"
        rows={[
          ["Frontend", info.urls.frontend_url],
          ["Public", info.urls.public_url],
        ]}
      />

      <Section title="Betalingen" rows={[["Mollie-modus", info.mollie_mode]]} />

      <div className="card p-4">
        <h2 className="font-bold text-blue-800 mb-3">Analytics</h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <div className="flex justify-between gap-4 border-b border-gray-100 py-1">
            <dt className="text-gray-600">Webstatistieken (Umami)</dt>
            <dd className="font-medium text-gray-900 text-right">
              {UMAMI_CONFIGURED ? "geconfigureerd" : "niet geconfigureerd"}
            </dd>
          </div>
          {UMAMI_DASHBOARD && (
            <div className="flex justify-between gap-4 border-b border-gray-100 py-1">
              <dt className="text-gray-600">Umami-dashboard</dt>
              <dd className="text-right break-all">
                <a href={UMAMI_DASHBOARD} target="_blank" rel="noopener noreferrer" className="font-medium text-blue-700 underline">
                  {UMAMI_DASHBOARD}
                </a>
              </dd>
            </div>
          )}
          {UMAMI_WEBSITE_ID && (
            <div className="flex justify-between gap-4 border-b border-gray-100 py-1">
              <dt className="text-gray-600">Website ID</dt>
              <dd className="font-medium text-gray-900 text-right break-all">{UMAMI_WEBSITE_ID}</dd>
            </div>
          )}
          <div className="flex justify-between gap-4 border-b border-gray-100 py-1">
            <dt className="text-gray-600">Business-events</dt>
            <dd className="text-right">
              <a href="/admin/analyse" className="font-medium text-blue-700 underline">admin → Analyse</a>
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
