"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { memberRequestLogin, memberVerifyOtp } from "@/lib/api";

export default function LedenLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [code, setCode] = useState("");
  const [otpLoading, setOtpLoading] = useState(false);
  const [otpError, setOtpError] = useState("");

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

  async function handleOtp(e: React.FormEvent) {
    e.preventDefault();
    setOtpLoading(true);
    setOtpError("");
    try {
      const res = await memberVerifyOtp(email, code.trim());
      localStorage.setItem("member_token", res.data.access_token);
      router.push("/");
    } catch {
      setOtpError("Ongeldige of verlopen code.");
    } finally {
      setOtpLoading(false);
    }
  }

  if (sent) {
    return (
      <div className="max-w-sm mx-auto mt-16">
        <div className="card">
          <h1 className="text-2xl font-bold text-blue-800 mb-4">Controleer je e-mail</h1>
          <p className="text-gray-600 mb-6">
            Als <strong>{email}</strong> bij ons gekend is, ontvang je een inloglink.
            De link is 15 minuten geldig.
          </p>
          <form onSubmit={handleOtp} className="space-y-3 border-t pt-4">
            <label className="label">Of voer de 6-cijferige code uit je e-mail in</label>
            <input
              className="input tracking-widest text-center"
              inputMode="numeric"
              maxLength={6}
              placeholder="123456"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            />
            {otpError && <p className="text-red-600 text-sm">{otpError}</p>}
            <button type="submit" disabled={otpLoading || code.length !== 6} className="btn-primary w-full">
              {otpLoading ? "Bezig…" : "Inloggen met code"}
            </button>
          </form>
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
