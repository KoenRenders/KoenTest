"use client";
import { useEffect, useState } from "react";
import { getIdeas, markIdeaReviewed } from "@/lib/api";
import type { Idea } from "@/lib/types";

export default function AdminIdeeen() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [filter, setFilter] = useState<"all" | "open" | "reviewed">("open");

  function load() {
    getIdeas().then((r) => setIdeas(r.data)).catch(() => {});
  }

  useEffect(() => { load(); }, []);

  async function handleReview(id: number) {
    await markIdeaReviewed(id);
    load();
  }

  const filtered = ideas.filter((i) => {
    if (filter === "open") return !i.is_reviewed;
    if (filter === "reviewed") return i.is_reviewed;
    return true;
  });

  return (
    <div>
      <h1 className="text-2xl font-bold text-blue-800 mb-4">Ideeënbus</h1>
      <div className="flex gap-2 mb-4">
        {(["open", "reviewed", "all"] as const).map((f) => (
          <button key={f} className={filter === f ? "btn-primary btn-sm" : "btn-secondary btn-sm"} onClick={() => setFilter(f)}>
            {f === "open" ? "Ongelezen" : f === "reviewed" ? "Behandeld" : "Alle"}
          </button>
        ))}
      </div>
      <div className="space-y-3">
        {filtered.map((idea) => (
          <div key={idea.id} className="card">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <div className="font-medium">{idea.submitter_name}
                  {idea.submitter_email && <span className="text-gray-500 font-normal text-sm ml-2">({idea.submitter_email})</span>}
                </div>
                <p className="mt-2 text-gray-700 whitespace-pre-wrap">{idea.content}</p>
                <p className="mt-1 text-xs text-gray-400">{new Date(idea.submitted_at).toLocaleDateString("nl-BE", { day: "2-digit", month: "long", year: "numeric" })}</p>
              </div>
              {!idea.is_reviewed && (
                <button className="btn-primary btn-sm whitespace-nowrap" onClick={() => handleReview(idea.id)}>
                  Markeer behandeld
                </button>
              )}
              {idea.is_reviewed && (
                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full whitespace-nowrap">✓ Behandeld</span>
              )}
            </div>
          </div>
        ))}
        {filtered.length === 0 && <p className="text-gray-500 text-sm">Geen ideeën in deze categorie.</p>}
      </div>
    </div>
  );
}
