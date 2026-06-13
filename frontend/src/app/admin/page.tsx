"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getStats } from "@/lib/api";

interface Stats {
  members: number;
  active_members: number;
  upcoming_activities: number;
  open_ideas: number;
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    getStats().then((r) => setStats(r.data)).catch(() => {});
  }, []);

  const tiles = stats ? [
    { label: "Leden", value: stats.members, color: "bg-blue-50 text-blue-800", href: "/admin/leden" },
    { label: "Actieve leden", value: stats.active_members, color: "bg-green-50 text-green-800", href: "/admin/leden" },
    { label: "Komende activiteiten", value: stats.upcoming_activities, color: "bg-purple-50 text-purple-800", href: "/admin/activiteiten" },
    { label: "Ongelezen ideeën", value: stats.open_ideas, color: "bg-yellow-50 text-yellow-800", href: "/admin/ideeen" },
  ] : [];

  return (
    <div>
      <h1 className="text-2xl font-bold text-blue-800 mb-6">Dashboard</h1>
      {stats ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          {tiles.map((t) => (
            <Link
              key={t.label}
              href={t.href}
              className={`block rounded-xl p-5 transition hover:shadow-md hover:brightness-95 cursor-pointer ${t.color}`}
            >
              <div className="text-3xl font-extrabold">{t.value}</div>
              <div className="text-sm font-medium mt-1">{t.label}</div>
            </Link>
          ))}
        </div>
      ) : (
        <p className="text-gray-500">Statistieken laden…</p>
      )}
    </div>
  );
}
