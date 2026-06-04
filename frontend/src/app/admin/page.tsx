"use client";
import { useEffect, useState } from "react";
import { getStats } from "@/lib/api";

interface Stats {
  families: number;
  active_members: number;
  upcoming_activities: number;
  open_ideas: number;
  pending_orders: number;
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    getStats().then((r) => setStats(r.data)).catch(() => {});
  }, []);

  const tiles = stats ? [
    { label: "Gezinnen", value: stats.families, color: "bg-blue-50 text-blue-800" },
    { label: "Actieve leden", value: stats.active_members, color: "bg-green-50 text-green-800" },
    { label: "Komende activiteiten", value: stats.upcoming_activities, color: "bg-purple-50 text-purple-800" },
    { label: "Ongelezen ideeën", value: stats.open_ideas, color: "bg-yellow-50 text-yellow-800" },
    { label: "Openstaande bestellingen", value: stats.pending_orders, color: "bg-orange-50 text-orange-800" },
  ] : [];

  return (
    <div>
      <h1 className="text-2xl font-bold text-blue-800 mb-6">Dashboard</h1>
      {stats ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          {tiles.map((t) => (
            <div key={t.label} className={`rounded-xl p-5 ${t.color}`}>
              <div className="text-3xl font-extrabold">{t.value}</div>
              <div className="text-sm font-medium mt-1">{t.label}</div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-gray-500">Statistieken laden…</p>
      )}
    </div>
  );
}
