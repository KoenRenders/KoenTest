"use client";
import { useState } from "react";
import { memberRequestLogin } from "@/lib/api";

export default function LedenLoginPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await memberRequestLogin(email);
      setSent(true);
    } catch {
      setError("Er ging iets mis. Probeer opnieuw.");
    } finally {
      setLoading(false);
    }
  }

  if (sent) {
    return (
      <div className="max-w-sm mx-auto mt-16">
        <div className="card">
          <h1 className="text-2xl font-bold text-blue-800 mb-4">Controleer je e-mail</h1>
          <p className="text-gray-600">
            Als <strong>{email}</strong> bij ons gekend is, ontvang je een inloglink.
            De link is 15 minuten geldig.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <div className="card">
        <h1 className="text-2xl font-bold text-blue-800 mb-2">Inloggen als lid</h1>
        <p className="text-gray-600 text-sm mb-6">
          Vul het e-mailadres in dat bij je lidmaatschap gekend is. Je ontvangt een inloglink.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">E-mailadres</label>
            <input
              type="email"
              className="input"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          {error && <p className="text-red-600 text-sm">{error}</p>}
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? "Bezig…" : "Stuur inloglink"}
          </button>
        </form>
      </div>
    </div>
  );
}
