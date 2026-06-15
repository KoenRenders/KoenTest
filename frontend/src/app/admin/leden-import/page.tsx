"use client";
import { useRef, useState } from "react";
import {
  memberImportPreview,
  memberImportCommit,
  type MemberImportPreview,
  type MemberImportResult,
  type MemberImportReport,
} from "@/lib/api";
import { parseApiError } from "@/lib/errors";

function ReportSummary({ r }: { r: MemberImportReport }) {
  const items: [string, number][] = [
    ["Nieuwe gezinnen", r.new_families],
    ["Bijgewerkte gezinnen", r.updated_families],
    ["Personen toegevoegd", r.persons_added],
    ["Personen bijgewerkt", r.persons_updated],
    ["Personen verwijderd", r.persons_removed],
    ["Lidmaatschappen", r.memberships_created],
    ["Admin-gebruikers", r.admins_created],
    ["Overgeslagen", r.skipped],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {items.map(([label, n]) => (
        <div key={label} className="rounded border border-gray-200 p-3 text-center">
          <div className="text-2xl font-semibold">{n}</div>
          <div className="text-xs text-gray-500">{label}</div>
        </div>
      ))}
    </div>
  );
}

export default function LedenImport() {
  const [file, setFile] = useState<File | null>(null);
  const [allMembers, setAllMembers] = useState(false);
  const [preview, setPreview] = useState<MemberImportPreview | null>(null);
  const [result, setResult] = useState<MemberImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showDetails, setShowDetails] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function reset() {
    setPreview(null);
    setResult(null);
    setError("");
    setShowDetails(false);
  }

  function onPick(f: File | null) {
    setFile(f);
    reset();
  }

  async function doPreview(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const r = await memberImportPreview(file, allMembers);
      setPreview(r.data);
    } catch (err) {
      setError(parseApiError(err, "Kon het bestand niet controleren."));
    } finally {
      setBusy(false);
    }
  }

  async function doCommit() {
    if (!preview) return;
    if (!confirm(
      `Definitief importeren? Dit overschrijft de ledendata met de Excel ` +
      `(${preview.selected_families} gezinnen, ${preview.total_persons} personen).`
    )) return;
    setBusy(true);
    setError("");
    try {
      const r = await memberImportCommit(preview.token);
      setResult(r.data);
      setPreview(null);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch (err) {
      setError(parseApiError(err, "Importeren mislukt. Controleer en laad opnieuw op."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Ledenrapport importeren</h1>
        <p className="mt-1 text-sm text-gray-600">
          Laad het Raak-Nationaal-ledenrapport (.xls) op. Bekijk eerst de
          droogloop, bevestig daarna om de wijzigingen door te voeren. De Excel is
          de bron van waarheid: bestaande gezinnen worden bijgewerkt en personen
          die niet meer in het bestand staan, worden uit hun gezin verwijderd.
        </p>
      </div>

      <form onSubmit={doPreview} className="space-y-4 rounded border border-gray-200 p-4">
        <input
          ref={fileRef}
          type="file"
          accept=".xls"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
          className="block text-sm"
        />
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={allMembers}
            onChange={(e) => { setAllMembers(e.target.checked); reset(); }}
          />
          Ook buiten productie alle leden laden (anders enkel de testadressen)
        </label>
        <button
          type="submit"
          disabled={!file || busy}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {busy && !preview ? "Bezig…" : "Controleer (droogloop)"}
        </button>
      </form>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-3 rounded border border-green-300 bg-green-50 p-4">
          <h2 className="font-semibold text-green-800">Import voltooid</h2>
          <ReportSummary r={result.report} />
          {result.report.warnings.length > 0 && (
            <ul className="list-disc pl-5 text-sm text-amber-700">
              {result.report.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </div>
      )}

      {preview && (
        <div className="space-y-3 rounded border border-gray-200 p-4">
          <h2 className="font-semibold">
            Droogloop — {preview.selected_families} gezinnen, {preview.total_persons} personen
            {!preview.load_all && " (testadressen)"}
          </h2>
          <ReportSummary r={preview.report} />

          {preview.report.warnings.length > 0 && (
            <ul className="list-disc pl-5 text-sm text-amber-700">
              {preview.report.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}

          {preview.report.lines.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setShowDetails((s) => !s)}
                className="text-sm text-blue-600 underline"
              >
                {showDetails ? "Verberg details" : "Toon details per gezin"}
              </button>
              {showDetails && (
                <pre className="mt-2 max-h-96 overflow-auto rounded bg-gray-50 p-3 text-xs">
                  {preview.report.lines.join("\n")}
                </pre>
              )}
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              onClick={doCommit}
              disabled={busy}
              className="rounded bg-green-600 px-4 py-2 text-white disabled:opacity-50"
            >
              {busy ? "Bezig…" : "Definitief importeren"}
            </button>
            <button
              onClick={reset}
              disabled={busy}
              className="rounded border border-gray-300 px-4 py-2"
            >
              Annuleren
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
