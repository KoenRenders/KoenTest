"use client";
import { useCallback, useEffect, useState } from "react";
import { getMemberChanges, exportMemberChanges } from "@/lib/api";
import { parseApiError } from "@/lib/errors";

interface Change {
  recorded_at: string;
  entity: string;
  entity_id: number | null;
  operation: string;
  operation_label: string;
  action: string;
  actor: string | null;
  summary: string;
}

const OP_COLORS: Record<string, string> = {
  Toegevoegd: "bg-green-100 text-green-700",
  Gewijzigd: "bg-yellow-100 text-yellow-800",
  Verwijderd: "bg-red-100 text-red-700",
};

function defaultSince() {
  return `${new Date().getFullYear()}-01-01`;
}

export default function LedenwijzigingenPage() {
  const [since, setSince] = useState(defaultSince());
  const [rows, setRows] = useState<Change[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (sinceValue: string) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await getMemberChanges(sinceValue);
      setRows(resp.data);
    } catch (e) {
      setError(parseApiError(e, "Kon de wijzigingen niet laden."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(since); }, [load, since]);

  async function download() {
    try {
      const resp = await exportMemberChanges(since);
      const url = URL.createObjectURL(resp.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `ledenwijzigingen-vanaf-${since}.ods`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(parseApiError(e, "Export mislukt."));
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Ledenwijzigingen</h1>
      <p className="text-sm text-gray-500 mb-6">
        Alle wijzigingen aan ledendata sinds de gekozen datum, om manueel over te nemen in Raak Nationaal.
      </p>

      <div className="flex items-end gap-3 mb-6 flex-wrap">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Sinds</label>
          <input
            type="date"
            className="input text-sm"
            value={since}
            onChange={(e) => setSince(e.target.value)}
          />
        </div>
        <button onClick={download} className="btn-secondary text-sm" disabled={rows.length === 0}>
          Export .ods
        </button>
        <span className="text-sm text-gray-500 ml-auto">
          {loading ? "Laden…" : `${rows.length} wijziging${rows.length !== 1 ? "en" : ""}`}
        </span>
      </div>

      {error && (
        <p className="mb-4 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-3">{error}</p>
      )}

      {!loading && rows.length === 0 ? (
        <p className="text-gray-500 italic">Geen wijzigingen sinds {since}.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-200">
                <th className="py-2 pr-3 font-medium">Tijdstip</th>
                <th className="py-2 pr-3 font-medium">Wat</th>
                <th className="py-2 pr-3 font-medium">Type</th>
                <th className="py-2 pr-3 font-medium">Details</th>
                <th className="py-2 pr-3 font-medium">Door</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-gray-100 align-top">
                  <td className="py-2 pr-3 whitespace-nowrap text-gray-500">
                    {new Date(r.recorded_at).toLocaleString("nl-BE")}
                  </td>
                  <td className="py-2 pr-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${OP_COLORS[r.operation_label] ?? "bg-gray-100 text-gray-600"}`}>
                      {r.operation_label}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-gray-700">{r.entity}</td>
                  <td className="py-2 pr-3 text-gray-800">{r.summary}</td>
                  <td className="py-2 pr-3 text-gray-500 whitespace-nowrap">{r.actor ?? "systeem"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
