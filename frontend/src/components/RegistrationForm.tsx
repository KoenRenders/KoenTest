"use client";
import { useState } from "react";
import { registerForActivity } from "@/lib/api";
import type { Activity } from "@/lib/types";

interface Props {
  activity: Activity;
  onClose: () => void;
  onSuccess: () => void;
}

export default function RegistrationForm({ activity, onClose, onSuccess }: Props) {
  const [form, setForm] = useState({ contact_name: "", contact_email: "", family_id: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await registerForActivity(activity.id, {
        contact_name: form.contact_name,
        contact_email: form.contact_email || undefined,
        family_id: form.family_id ? parseInt(form.family_id) : undefined,
        registration_type: activity.registration_type,
      });
      onSuccess();
    } catch {
      setError("Er is iets misgelopen. Probeer opnieuw.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6">
        <h2 className="text-xl font-bold mb-1">Inschrijven</h2>
        <p className="text-gray-600 mb-6">{activity.name} – {new Date(activity.date).toLocaleDateString("nl-BE")}</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Naam *</label>
            <input
              className="input"
              required
              value={form.contact_name}
              onChange={(e) => setForm((f) => ({ ...f, contact_name: e.target.value }))}
            />
          </div>
          <div>
            <label className="label">E-mailadres</label>
            <input
              type="email"
              className="input"
              value={form.contact_email}
              onChange={(e) => setForm((f) => ({ ...f, contact_email: e.target.value }))}
            />
          </div>
          <div>
            <label className="label">Gezinsnummer (als lid)</label>
            <input
              type="number"
              className="input"
              placeholder="Optioneel – voor ledenkorting"
              value={form.family_id}
              onChange={(e) => setForm((f) => ({ ...f, family_id: e.target.value }))}
            />
          </div>
          {error && <p className="text-red-600 text-sm">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="submit" disabled={loading} className="btn-primary flex-1">
              {loading ? "Bezig…" : "Inschrijven"}
            </button>
            <button type="button" onClick={onClose} className="btn-secondary flex-1">
              Annuleren
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
