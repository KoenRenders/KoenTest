"use client";
import { useEffect, useState } from "react";
import { getArchivedActivities, getActivityPhotoAvailability } from "@/lib/api";
import ActivityList from "@/components/ActivityList";
import type { Activity } from "@/lib/types";

export default function ArchiefPage() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [photoActivityIds, setPhotoActivityIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Twee requests totaal: de activiteitenlijst + welke activiteiten foto's
    // hebben. Geen losse fotorequest meer per activiteit.
    Promise.all([getArchivedActivities(), getActivityPhotoAvailability()])
      .then(([a, p]) => {
        setActivities(a.data);
        setPhotoActivityIds(p.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="text-3xl font-bold text-blue-800 mb-2">Archief</h1>
      <p className="text-gray-600 mb-8">Overzicht van alle voorbije activiteiten.</p>
      {loading ? (
        <p className="text-gray-500">Laden…</p>
      ) : (
        <ActivityList
          activities={activities}
          showRegister={false}
          showPhotos
          photoActivityIds={photoActivityIds}
        />
      )}
    </div>
  );
}
