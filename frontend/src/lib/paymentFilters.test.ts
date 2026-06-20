import { describe, it, expect } from "vitest";
import { matchesPaymentFilter, saldoOf, type FilterablePayment, type PaymentFilter } from "@/lib/paymentFilters";

const ALL: PaymentFilter = { status: "all", context: "all" };

function rec(p: Partial<FilterablePayment>): FilterablePayment {
  return {
    amount: "50.00", amount_paid: null, status: "pending",
    payable_type: "membership", component_id: null, membership_year: 2025,
    ...p,
  };
}

describe("matchesPaymentFilter — lidgeld-jaar via context 'year-<jaar>' (#308)", () => {
  it("isoleert het jaar: year-2025 toont geen 2024-record", () => {
    expect(matchesPaymentFilter(rec({ membership_year: 2024 }), { ...ALL, context: "year-2025" })).toBe(false);
    expect(matchesPaymentFilter(rec({ membership_year: 2025 }), { ...ALL, context: "year-2025" })).toBe(true);
  });

  it("verbergt niet-lidgeld zodra een jaar gekozen is", () => {
    const activity = rec({ payable_type: "registration", membership_year: null, component_id: 7 });
    expect(matchesPaymentFilter(activity, { ...ALL, context: "year-2025" })).toBe(false);
  });

  it("context=membership toont alle lidgeld-jaren", () => {
    expect(matchesPaymentFilter(rec({ membership_year: 2024 }), { ...ALL, context: "membership" })).toBe(true);
    expect(matchesPaymentFilter(rec({ membership_year: 2025 }), { ...ALL, context: "membership" })).toBe(true);
  });

  it("context=all toont alles (geen regressie op bestaand gedrag)", () => {
    expect(matchesPaymentFilter(rec({ membership_year: 2024 }), ALL)).toBe(true);
    const activity = rec({ payable_type: "registration", membership_year: null, component_id: 1 });
    expect(matchesPaymentFilter(activity, ALL)).toBe(true);
  });

  it("combineert met status: year-2025 + enkel openstaand laat een vereffend record vallen", () => {
    const betaald = rec({ membership_year: 2025, amount: "50.00", amount_paid: "50.00" });
    expect(matchesPaymentFilter(betaald, { status: "openstaand", context: "year-2025" })).toBe(false);
    const open = rec({ membership_year: 2025, amount: "50.00", amount_paid: "10.00" });
    expect(matchesPaymentFilter(open, { status: "openstaand", context: "year-2025" })).toBe(true);
  });
});

describe("matchesPaymentFilter — bestaande context/status blijven werken", () => {
  it("context=membership verbergt activiteit-inschrijvingen", () => {
    const activity = rec({ payable_type: "registration", membership_year: null, component_id: 3 });
    expect(matchesPaymentFilter(activity, { status: "all", context: "membership" })).toBe(false);
    expect(matchesPaymentFilter(rec({}), { status: "all", context: "membership" })).toBe(true);
  });

  it("context=comp-<id> matcht enkel dat onderdeel", () => {
    const c5 = rec({ payable_type: "registration", membership_year: null, component_id: 5 });
    const c9 = rec({ payable_type: "registration", membership_year: null, component_id: 9 });
    expect(matchesPaymentFilter(c5, { status: "all", context: "comp-5" })).toBe(true);
    expect(matchesPaymentFilter(c9, { status: "all", context: "comp-5" })).toBe(false);
  });

  it("status=paid/pending kijkt naar de status-badge; openstaand naar het saldo", () => {
    expect(matchesPaymentFilter(rec({ status: "paid" }), { status: "paid", context: "all" })).toBe(true);
    expect(matchesPaymentFilter(rec({ status: "pending" }), { status: "paid", context: "all" })).toBe(false);
  });
});

describe("saldoOf", () => {
  it("trekt betaald van te-betalen af", () => {
    expect(saldoOf(rec({ amount: "50.00", amount_paid: "20.00" }))).toBeCloseTo(30);
    expect(saldoOf(rec({ amount: "50.00", amount_paid: null }))).toBeCloseTo(50);
  });
});
