interface RegistrationItem {
  product_name?: string | null;
  quantity: number;
  subtotal?: number | null;
}

export interface RegistrationEntry {
  contact_name?: string | null;
  contact_email?: string | null;
  phone?: string | null;
  team_name?: string | null;
  payment_method?: string | null;
  remarks?: string | null;
  items: RegistrationItem[];
}

interface Props {
  entries: RegistrationEntry[];
}

function fmtPaymentMethod(m: string) {
  if (m === "ONLINE") return "Online";
  if (m === "OVERSCHRIJVING") return "Overschrijving";
  return m;
}

export default function RegistrationList({ entries }: Props) {
  if (entries.length === 0) {
    return <p className="text-gray-500 text-sm">Geen inschrijvingen.</p>;
  }

  return (
    <ul className="space-y-2 text-sm">
      {entries.map((entry, i) => (
        <li key={i} className="border-b border-gray-100 pb-2 last:border-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              {entry.contact_name && (
                <span className="font-medium">{entry.contact_name}</span>
              )}
              {entry.contact_email && (
                <span className="text-gray-400 ml-2 text-xs">{entry.contact_email}</span>
              )}
              {entry.phone && (
                <span className="text-gray-400 ml-2 text-xs">📱 {entry.phone}</span>
              )}
              {entry.team_name && (
                <span className="ml-2 text-blue-600 text-xs">🏅 {entry.team_name}</span>
              )}
            </div>
            {entry.payment_method && (
              <span className="text-xs text-gray-500 whitespace-nowrap">
                {fmtPaymentMethod(entry.payment_method)}
              </span>
            )}
          </div>
          {entry.items.length > 0 && (
            <ul className="mt-1 pl-3 text-xs text-gray-500 space-y-0.5">
              {entry.items.map((it, j) => (
                <li key={j} className="flex justify-between gap-4">
                  <span>{it.product_name ?? "—"} × {it.quantity}</span>
                  {it.subtotal != null && (
                    <span className="tabular-nums">€{it.subtotal.toFixed(2)}</span>
                  )}
                </li>
              ))}
              <li className="flex justify-between gap-4 border-t border-gray-200 pt-0.5 font-medium text-gray-700">
                <span>Totaal</span>
                <span className="tabular-nums">
                  €{entry.items.reduce((s, it) => s + (it.subtotal ?? 0), 0).toFixed(2)}
                </span>
              </li>
            </ul>
          )}
          {entry.remarks && (
            <p className="mt-1 pl-3 text-xs text-amber-700 italic">💬 {entry.remarks}</p>
          )}
        </li>
      ))}
    </ul>
  );
}
