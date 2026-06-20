// Pure filter-logica voor de admin-betalingenpagina (#90 context, #83 status,
// #308 lidgeld-jaar). Bewust losgekoppeld van de React-component zodat de
// invarianten in isolatie getest kunnen worden (Vitest) — geen browser, geen
// geseede stack. De component roept enkel `records.filter(r => matchesPaymentFilter(r, f))`.

export interface FilterablePayment {
  amount: string;
  amount_paid: string | null;
  status: string;
  payable_type: string;          // "registration" | "membership"
  component_id: number | null;
  membership_year: number | null; // lidgeld-jaar (#308); null voor niet-lidgeld
}

export interface PaymentFilter {
  status: "all" | "openstaand" | "pending" | "paid";
  // Eén gecombineerd context-filter (#90/#308):
  //   "all" | "membership" (alle lidgeld) | "year-<jaar>" (lidgeld van dat jaar) | "comp-<id>"
  context: string;
}

/** Saldo = te betalen − betaald. Positief = openstaand. */
export function saldoOf(r: FilterablePayment): number {
  return parseFloat(r.amount) - (r.amount_paid ? parseFloat(r.amount_paid) : 0);
}

/** Hoort dit record in de huidige weergave, gegeven het actieve filter? */
export function matchesPaymentFilter(r: FilterablePayment, f: PaymentFilter): boolean {
  // Context-filter: lidmaatschap (alle jaren of één jaar) of één activiteit-onderdeel.
  if (f.context === "membership" && r.payable_type !== "membership") return false;
  if (f.context.startsWith("year-")) {
    const y = parseInt(f.context.slice(5), 10);
    if (r.payable_type !== "membership" || r.membership_year !== y) return false;
  }
  if (f.context.startsWith("comp-")) {
    const cid = parseInt(f.context.slice(5), 10);
    if (r.payable_type !== "registration" || r.component_id !== cid) return false;
  }

  // Status-filter (#83): betaald/openstaand uit het saldo (betaald = waarheid, #198).
  if (f.status === "pending") return r.status === "pending";
  if (f.status === "paid") return r.status === "paid";
  if (f.status === "openstaand") return saldoOf(r) > 0.001;
  return true;
}
