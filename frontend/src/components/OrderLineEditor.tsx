"use client";
import { useState } from "react";
import Link from "next/link";
import { addOrderLine, updateOrderLine, deleteOrderLine, updateRegistrationRemarks } from "@/lib/api";
import { parseApiError } from "@/lib/errors";

export interface EditableItem {
  id?: number | null;
  product_id: number;
  quantity: number;
  product_name?: string | null;
}

export interface ProductOption {
  id: number;
  name: string;
}

interface Balance {
  total_due: number;
  total_paid: number;
  total_refunded: number;
  balance: number;
}

interface ApiResult {
  balance: Balance;
  refund_due: boolean;
}

interface Props {
  activityId: number;
  registrationId: number;
  items: EditableItem[];
  products: ProductOption[];
  /** Huidige opmerking van de inschrijver (#283), bewerkbaar door de admin. */
  remarks?: string | null;
  /** Parent herlaadt de inschrijvingen na een wijziging. */
  onChanged: () => void;
}

/**
 * Bewerk de bestelregels van één inschrijving (#84): aantal wijzigen, regel
 * toevoegen of verwijderen. Geen in-place product-swap — vervang door de oude
 * regel te verwijderen en een nieuwe toe te voegen. Na elke wijziging tonen we
 * het herberekende saldo en, bij een negatief saldo, een verwijzing naar de
 * terugbetaal-flow in Betalingen.
 */
export default function OrderLineEditor({ activityId, registrationId, items, products, remarks, onChanged }: Props) {
  const [qtyDraft, setQtyDraft] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApiResult | null>(null);
  const [addProductId, setAddProductId] = useState<string>("");
  const [addQty, setAddQty] = useState<string>("1");
  const [remarksDraft, setRemarksDraft] = useState<string>(remarks ?? "");

  async function run(action: () => Promise<{ data: ApiResult }>) {
    setBusy(true);
    setError(null);
    try {
      const resp = await action();
      setResult(resp.data);
      onChanged();
    } catch (e) {
      setError(parseApiError(e, "Bewerken van de bestelregel mislukt."));
    } finally {
      setBusy(false);
    }
  }

  // Eén bewaarknop voor de hele inschrijving: sla in één klik elk gewijzigd
  // aantal én een gewijzigde opmerking (#283) op. De penningmeester hoeft niet
  // per regel of veld apart te bewaren.
  async function saveAll() {
    const changed: { id: number; q: number }[] = [];
    for (const it of items) {
      if (it.id == null) continue;
      const raw = qtyDraft[it.id];
      if (raw === undefined) continue;
      const q = parseInt(raw, 10);
      if (!q || q < 1) {
        setError("Aantal moet minstens 1 zijn (verwijder de regel om ze te schrappen).");
        return;
      }
      if (q !== it.quantity) changed.push({ id: it.id, q });
    }
    if (changed.length === 0 && !remarksChanged) return;
    setBusy(true);
    setError(null);
    try {
      let last: ApiResult | null = null;
      for (const c of changed) {
        const resp = await updateOrderLine(activityId, registrationId, c.id, { quantity: c.q });
        last = resp.data;
      }
      if (remarksChanged) {
        await updateRegistrationRemarks(activityId, registrationId, { remarks: remarksDraft.trim() || null });
      }
      if (last) setResult(last);
      setQtyDraft({});
      onChanged();
    } catch (e) {
      setError(parseApiError(e, "Bewerken van de inschrijving mislukt."));
    } finally {
      setBusy(false);
    }
  }

  function removeLine(item: EditableItem) {
    if (item.id == null) return;
    run(() => deleteOrderLine(activityId, registrationId, item.id!));
  }

  function addLine() {
    const pid = parseInt(addProductId, 10);
    const q = parseInt(addQty, 10);
    if (!pid) { setError("Kies een product om toe te voegen."); return; }
    if (!q || q < 1) { setError("Aantal moet minstens 1 zijn."); return; }
    run(() => addOrderLine(activityId, registrationId, { product_id: pid, quantity: q }))
      .then(() => { setAddProductId(""); setAddQty("1"); });
  }

  // Is er minstens één regel met een gewijzigd (en geldig afwijkend) aantal?
  const hasChanges = items.some(
    (it) => it.id != null && qtyDraft[it.id] !== undefined
      && parseInt(qtyDraft[it.id] ?? "", 10) !== it.quantity,
  );
  // Is de opmerking gewijzigd t.o.v. de opgeslagen waarde (#283)? Genormaliseerd
  // op trim zodat louter spaties geen "wijziging" zijn.
  const remarksChanged = remarksDraft.trim() !== (remarks ?? "").trim();

  return (
    <div className="mt-2 border-t border-gray-100 pt-2">
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={it.id ?? i} className="flex items-center gap-2 text-sm">
            <span className="flex-1 truncate">{it.product_name ?? `Product ${it.product_id}`}</span>
            <input
              type="number"
              min="1"
              className="input w-16 text-sm py-0.5"
              // Controlled: toont de lokale bewerking, anders het actuele aantal uit de
              // (herladen) data — zo volgt het scherm een samenvoeging van eenzelfde
              // product meteen (#197).
              value={it.id != null && qtyDraft[it.id] !== undefined ? qtyDraft[it.id] : String(it.quantity)}
              onChange={(e) => it.id != null && setQtyDraft((d) => ({ ...d, [it.id!]: e.target.value }))}
              disabled={busy || it.id == null}
            />
            <button
              onClick={() => removeLine(it)}
              disabled={busy || it.id == null}
              className="text-xs text-red-600 border border-red-200 rounded px-2 py-0.5 hover:bg-red-50 disabled:opacity-40"
              title="Regel verwijderen"
            >
              🗑
            </button>
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-2 mt-2">
        <select
          className="input flex-1 text-sm py-0.5"
          value={addProductId}
          onChange={(e) => setAddProductId(e.target.value)}
          disabled={busy}
        >
          <option value="">+ Product toevoegen…</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <input
          type="number"
          min="1"
          className="input w-16 text-sm py-0.5"
          value={addQty}
          onChange={(e) => setAddQty(e.target.value)}
          disabled={busy}
        />
        <button
          onClick={addLine}
          disabled={busy || !addProductId}
          className="text-xs text-green-700 border border-green-200 rounded px-2 py-0.5 hover:bg-green-50 disabled:opacity-40"
        >
          Toevoegen
        </button>
      </div>

      <div className="mt-2">
        <label className="block text-xs text-gray-500 mb-0.5">Opmerkingen</label>
        <textarea
          className="input w-full text-sm py-1"
          rows={2}
          value={remarksDraft}
          onChange={(e) => setRemarksDraft(e.target.value)}
          disabled={busy}
          placeholder="Opmerking van de inschrijver…"
        />
      </div>

      <div className="flex justify-end mt-2">
        <button
          onClick={saveAll}
          disabled={busy || (!hasChanges && !remarksChanged)}
          className="text-xs text-blue-600 border border-blue-200 rounded px-3 py-0.5 hover:bg-blue-50 disabled:opacity-40"
        >
          Bewaar
        </button>
      </div>

      {error && <p className="text-red-600 text-xs mt-2">{error}</p>}

      {result && (
        <div className="mt-2 text-xs">
          <span className="text-gray-600">
            Verschuldigd €{result.balance.total_due.toFixed(2)} ·
            Betaald €{result.balance.total_paid.toFixed(2)} ·
            Saldo €{result.balance.balance.toFixed(2)}
          </span>
          {result.refund_due && (
            <p className="mt-1 text-orange-700 font-medium">
              Saldo negatief — er is automatisch een terugbetaling aangemaakt.{" "}
              <Link href="/admin/betalingen" className="underline">Bevestig de terugstorting in Betalingen →</Link>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
