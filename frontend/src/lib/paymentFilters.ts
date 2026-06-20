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
  context: string;     // "all" | "membership" | "comp-<id>"
  year: number | null; // lidgeld-jaar, null = alle jaren (#308)
}

/** Saldo = te betalen − betaald. Positief = openstaand. */
export function saldoOf(r: FilterablePayment): number {
  return parseFloat(r.amount) - (r.amount_paid ? parseFloat(r.amount_paid) : 0);
}

/** Hoort dit record in de huidige weergave, gegeven het actieve filter? */
export function matchesPaymentFilter(r: FilterablePayment, f: PaymentFilter): boolean {
  // Context-filter (#90): lidmaatschap-vernieuwing of één activiteit-onderdeel.
  if (f.context === "membership" && r.payable_type !== "membership") return false;
  if (f.context.startsWith("comp-")) {
    const cid = parseInt(f.context.slice(5), 10);
    if (r.payable_type !== "registration" || r.component_id !== cid) return false;
  }

  // Lidgeld-jaar (#308): enkel lidmaatschapsrecords van dat jaar. Niet-lidgeld
  // (membership_year === null) valt weg zodra een jaar gekozen is.
  if (f.year !== null && r.membership_year !== f.year) return false;

  // Status-filter (#83): betaald/openstaand uit het saldo (betaald = waarheid, #198).
  if (f.status === "pending") return r.status === "pending";
  if (f.status === "paid") return r.status === "paid";
  if (f.status === "openstaand") return saldoOf(r) > 0.001;
  return true;
}
