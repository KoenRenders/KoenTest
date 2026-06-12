"use client";
import { useEffect, useRef, useState } from "react";
import {
  adminListMedia,
  uploadMedia,
  updateMedia,
  deleteMedia,
  getActivities,
  getArchivedActivities,
} from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import type { MediaAsset, Activity } from "@/lib/types";

type Tab = "sponsor" | "activity_photo";

export default function AdminMedia() {
  const [tab, setTab] = useState<Tab>("sponsor");
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [activityId, setActivityId] = useState<number | "">("");
  const [title, setTitle] = useState("");
  const [linkUrl, setLinkUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function load() {
    const params = tab === "activity_photo" && activityId !== ""
      ? { kind: tab, activity_id: activityId as number }
      : { kind: tab };
    adminListMedia(params).then((r) => setAssets(r.data)).catch(() => {});
  }

  useEffect(() => {
    Promise.all([getActivities(), getArchivedActivities()])
      .then(([a, b]) => setActivities([...a.data, ...b.data]))
      .catch(() => {});
  }, []);

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [tab, activityId]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const files = fileRef.current?.files ? Array.from(fileRef.current.files) : [];
    if (files.length === 0) { setError("Selecteer minstens één bestand."); return; }
    if (files.length > 20) { setError("Maximaal 20 bestanden per keer."); return; }
    if (tab === "activity_photo" && activityId === "") { setError("Kies eerst een activiteit."); return; }

    setUploading(true);
    try {
      await uploadMedia(files, {
        kind: tab,
        activity_id: tab === "activity_photo" ? (activityId as number) : undefined,
        title: title || undefined,
        link_url: tab === "sponsor" ? (linkUrl || undefined) : undefined,
      });
      setTitle("");
      setLinkUrl("");
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (err) {
      setError(parseApiError(err, "Upload mislukt."));
    } finally {
      setUploading(false);
    }
  }

  async function toggleActive(a: MediaAsset) {
    await updateMedia(a.id, { is_active: !a.is_active });
    load();
  }

  async function handleDelete(id: number) {
    if (!confirm("Dit bestand verwijderen?")) return;
    await deleteMedia(id);
    load();
  }

  async function saveTitle(a: MediaAsset, value: string) {
    if (value === (a.title || "")) return;
    await updateMedia(a.id, { title: value });
    load();
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-blue-800 mb-6">Media­bibliotheek</h1>

      <div className="flex gap-2 mb-6">
        <button
          className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === "sponsor" ? "bg-blue-700 text-white" : "bg-gray-100 text-gray-700"}`}
          onClick={() => setTab("sponsor")}
        >
          Sponsors
        </button>
        <button
          className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === "activity_photo" ? "bg-blue-700 text-white" : "bg-gray-100 text-gray-700"}`}
          onClick={() => setTab("activity_photo")}
        >
          Activiteitenfoto's
        </button>
      </div>

      <form onSubmit={handleUpload} className="card mb-6 space-y-4">
        <h2 className="font-bold text-lg">
          {tab === "sponsor" ? "Sponsorlogo's opladen" : "Foto's opladen"}
        </h2>

        {tab === "activity_photo" && (
          <div>
            <label className="label">Activiteit *</label>
            <select
              className="input"
              value={activityId}
              onChange={(e) => setActivityId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">— Kies een activiteit —</option>
              {activities.map((a) => (
                <option key={a.id} value={a.id}>{a.name} ({new Date(a.date).getFullYear()})</option>
              ))}
            </select>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">{tab === "sponsor" ? "Naam (alt-tekst)" : "Titel (optioneel)"}</label>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={tab === "sponsor" ? "bv. Mona" : ""} />
          </div>
          {tab === "sponsor" && (
            <div>
              <label className="label">Website (optioneel)</label>
              <input className="input" value={linkUrl} onChange={(e) => setLinkUrl(e.target.value)} placeholder="https://…" />
            </div>
          )}
        </div>

        <div>
          <label className="label">Bestanden (max. 20 tegelijk)</label>
          <input ref={fileRef} type="file" accept="image/*" multiple className="block text-sm" />
          <p className="text-xs text-gray-500 mt-1">Afbeeldingen worden automatisch verkleind. Toegestaan: JPG, PNG, WebP, GIF.</p>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button type="submit" className="btn-primary" disabled={uploading}>
          {uploading ? "Bezig met opladen…" : "Opladen"}
        </button>
      </form>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
        {assets.map((a) => (
          <div key={a.id} className={`card !p-3 ${a.is_active ? "" : "opacity-50"}`}>
            <div className="aspect-square bg-gray-50 rounded mb-2 flex items-center justify-center overflow-hidden">
              <img src={a.thumb_url} alt={a.title || ""} className="max-w-full max-h-full object-contain" />
            </div>
            <input
              className="input !py-1 !text-sm mb-2"
              defaultValue={a.title || ""}
              onBlur={(e) => saveTitle(a, e.target.value)}
              placeholder="Titel"
            />
            {a.link_url && (
              <a href={a.link_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:underline block truncate mb-2">
                {a.link_url}
              </a>
            )}
            <div className="flex gap-2 text-xs">
              <button className="text-gray-600 hover:underline" onClick={() => toggleActive(a)}>
                {a.is_active ? "Verbergen" : "Tonen"}
              </button>
              <button className="text-red-600 hover:underline ml-auto" onClick={() => handleDelete(a.id)}>
                Verwijderen
              </button>
            </div>
          </div>
        ))}
        {assets.length === 0 && (
          <p className="text-gray-500 text-sm col-span-full">
            {tab === "activity_photo" && activityId === ""
              ? "Kies een activiteit om de foto's te tonen, of laad nieuwe op."
              : "Nog geen media."}
          </p>
        )}
      </div>
    </div>
  );
}
