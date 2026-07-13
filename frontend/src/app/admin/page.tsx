"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getStats } from "@/lib/api";

interface Stats {
  members: number;
  active_members: number;
  active_member_households: number;
  active_member_persons: number;
  upcoming_activities: number;
  open_tasks: number;
  outstanding_balance: number;
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    getStats().then((r) => setStats(r.data)).catch(() => {});
  }, []);

  const tiles = stats ? [
    { label: "Leden", value: stats.members, color: "bg-blue-50 text-blue-800", href: "/admin/leden" },
    { label: "Actieve leden", value: stats.active_members, color: "bg-green-50 text-green-800", href: "/admin/leden" },
    { label: "Leden (personen)", value: stats.active_member_persons, color: "bg-teal-50 text-teal-800", href: "/admin/leden" },
    { label: "Komende activiteiten", value: stats.upcoming_activities, color: "bg-purple-50 text-purple-800", href: "/admin/activiteiten" },
    { label: "Open taken (werkbank)", value: stats.open_tasks, color: "bg-yellow-50 text-yellow-800", href: "/admin/werkbank" },
    { label: "Openstaand saldo", value: `€${stats.outstanding_balance.toFixed(2)}`, color: "bg-orange-50 text-orange-800", href: "/admin/betalingen" },
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
