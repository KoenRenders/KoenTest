"use client";
import { useParams } from "next/navigation";
import Link from "next/link";
import PhotoGallery from "@/components/PhotoGallery";

export default function ActiviteitFotosPage() {
  const params = useParams();
  const id = Number(params?.id);

  return (
    <div>
      <Link href="/archief" className="text-blue-700 hover:underline text-sm">← Terug naar archief</Link>
      <h1 className="text-3xl font-bold text-blue-800 mt-2 mb-6">Foto&apos;s</h1>
      {Number.isFinite(id) ? (
        <PhotoGallery activityId={id} />
      ) : (
        <p className="text-gray-500">Activiteit niet gevonden.</p>
      )}
    </div>
  );
}
