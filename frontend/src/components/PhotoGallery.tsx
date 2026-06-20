"use client";
import { useEffect, useState } from "react";
import Image from "next/image";
import { getActivityPhotos } from "@/lib/api";
import type { MediaAsset } from "@/lib/types";

export default function PhotoGallery({ activityId }: { activityId: number }) {
  const [photos, setPhotos] = useState<MediaAsset[]>([]);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    getActivityPhotos(activityId).then((r) => setPhotos(r.data)).catch(() => {});
  }, [activityId]);

  if (photos.length === 0) return null;

  const activeIdx = photos.findIndex((p) => p.id === active);

  return (
    <div className="mt-4">
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
        {photos.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setActive(p.id)}
            className="relative aspect-square overflow-hidden rounded-lg bg-gray-100 hover:opacity-90 transition-opacity"
          >
            {/* next/image met fill (#304): lazy-loading + geen layout-shift. unoptimized
                omdat thumb_url een dynamische backend-route is (geen vaste afmetingen). */}
            <Image
              src={p.thumb_url}
              alt={p.title || "Foto"}
              fill
              sizes="(max-width: 640px) 33vw, (max-width: 768px) 25vw, 16vw"
              className="object-cover"
              unoptimized
            />
          </button>
        ))}
      </div>

      {/* Lightbox */}
      {active !== null && activeIdx >= 0 && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setActive(null)}
        >
          <button
            type="button"
            aria-label="Sluiten"
            className="absolute top-4 right-4 text-white text-3xl leading-none"
            onClick={() => setActive(null)}
          >
            ×
          </button>
          {activeIdx > 0 && (
            <button
              type="button"
              aria-label="Vorige"
              className="absolute left-4 text-white text-4xl px-3"
              onClick={(e) => { e.stopPropagation(); setActive(photos[activeIdx - 1].id); }}
            >
              ‹
            </button>
          )}
          <img
            src={photos[activeIdx].url}
            alt={photos[activeIdx].title || "Foto"}
            className="max-h-[90vh] max-w-[90vw] object-contain rounded"
            onClick={(e) => e.stopPropagation()}
          />
          {activeIdx < photos.length - 1 && (
            <button
              type="button"
              aria-label="Volgende"
              className="absolute right-4 text-white text-4xl px-3"
              onClick={(e) => { e.stopPropagation(); setActive(photos[activeIdx + 1].id); }}
            >
              ›
            </button>
          )}
        </div>
      )}
    </div>
  );
}
