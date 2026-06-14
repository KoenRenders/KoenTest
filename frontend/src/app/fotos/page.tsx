"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getArchivedActivities, getActivityPhotoCovers } from "@/lib/api";
import type { Activity } from "@/lib/types";

function formatDate(d: string) {
  return new Date(d).toLocaleDateString("nl-BE", { year: "numeric", month: "long", day: "numeric" });
}

export default function FotosPage() {
  const [albums, setAlbums] = useState<Activity[]>([]);
  const [covers, setCovers] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getArchivedActivities(), getActivityPhotoCovers()])
      .then(([a, c]) => {
        const coverMap: Record<number, string> = {};
        c.data.forEach((row) => { coverMap[row.activity_id] = row.thumb_url; });
        setCovers(coverMap);
        setAlbums((a.data as Activity[]).filter((act) => act.id in coverMap));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const byYear = albums.reduce<Record<number, Activity[]>>((acc, a) => {
    const primary = a.sort_date || a.dates[0]?.start_date;
    const year = primary ? new Date(primary).getFullYear() : 0;
    (acc[year] = acc[year] || []).push(a);
    return acc;
  }, {});

  const years = Object.keys(byYear).map(Number).sort((a, b) => b - a);

  return (
    <div>
      <h1 className="text-3xl font-bold text-blue-800 mb-2">Foto&apos;s</h1>
      <p className="text-gray-600 mb-8">Alle fotoalbums van onze activiteiten.</p>
      {loading ? (
        <p className="text-gray-500">Laden…</p>
      ) : albums.length === 0 ? (
        <p className="text-gray-500 italic">Nog geen fotoalbums beschikbaar.</p>
      ) : (
        <div className="space-y-10">
          {years.map((year) => (
            <div key={year}>
              <h3 className="text-lg font-bold text-blue-800 mb-4 border-b border-blue-200 pb-2">{year}</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                {byYear[year].map((act) => (
                  <Link
                    key={act.id}
                    href={`/activiteiten/${act.id}/fotos`}
                    className="card !p-0 overflow-hidden hover:shadow-md transition-shadow"
                  >
                    <div className="aspect-video bg-gray-100 overflow-hidden">
                      <img
                        src={covers[act.id]}
                        alt={act.name}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                    </div>
                    <div className="p-4">
                      <div className="font-semibold text-blue-700">{act.name}</div>
                      <div className="text-sm text-gray-500 mt-1">{formatDate(act.date)}</div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
