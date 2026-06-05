"use client";
import { useState } from "react";
import { submitIdea } from "@/lib/api";

export default function IdeaBox() {
  const [form, setForm] = useState({ submitter_name: "", submitter_email: "", content: "" });
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    try {
      await submitIdea(form);
      setStatus("success");
      setForm({ submitter_name: "", submitter_email: "", content: "" });
    } catch {
      setStatus("error");
    }
  }

  return (
    <section className="card">
      <p className="text-gray-600 mb-4 text-sm">
        Heb je een idee voor een activiteit of suggestie voor de vereniging? Laat het ons weten!
      </p>
      {status === "success" ? (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-green-800">
          Bedankt voor je idee! We bekijken het zo snel mogelijk.
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Naam *</label>
              <input
                className="input"
                required
                value={form.submitter_name}
                onChange={(e) => setForm((f) => ({ ...f, submitter_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">E-mailadres</label>
              <input
                type="email"
                className="input"
                value={form.submitter_email}
                onChange={(e) => setForm((f) => ({ ...f, submitter_email: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="label">Jouw idee *</label>
            <textarea
              className="input min-h-[120px]"
              required
              value={form.content}
              onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
            />
          </div>
          {status === "error" && <p className="text-red-600 text-sm">Er is iets misgelopen. Probeer opnieuw.</p>}
          <button type="submit" disabled={status === "loading"} className="btn-primary w-full sm:w-auto">
            {status === "loading" ? "Bezig…" : "Idee versturen"}
          </button>
        </form>
      )}
    </section>
  );
}
