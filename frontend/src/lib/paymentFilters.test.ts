import { describe, it, expect } from "vitest";
import { matchesPaymentFilter, saldoOf, type FilterablePayment, type PaymentFilter } from "@/lib/paymentFilters";

const ALL: PaymentFilter = { status: "all", context: "all", year: null };

function rec(p: Partial<FilterablePayment>): FilterablePayment {
  return {
    amount: "50.00", amount_paid: null, status: "pending",
    payable_type: "membership", component_id: null, membership_year: 2025,
    ...p,
  };
}

describe("matchesPaymentFilter — lidgeld-jaar (#308)", () => {
  it("isoleert het jaar: 2025 toont geen 2024-record", () => {
    expect(matchesPaymentFilter(rec({ membership_year: 2024 }), { ...ALL, year: 2025 })).toBe(false);
    expect(matchesPaymentFilter(rec({ membership_year: 2025 }), { ...ALL, year: 2025 })).toBe(true);
  });

  it("verbergt niet-lidgeld (membership_year null) zodra een jaar gekozen is", () => {
    const activity = rec({ payable_type: "registration", membership_year: null, component_id: 7 });
    expect(matchesPaymentFilter(activity, { ...ALL, year: 2025 })).toBe(false);
  });

  it("year=null toont alle jaren (geen regressie op bestaand gedrag)", () => {
    expect(matchesPaymentFilter(rec({ membership_year: 2024 }), ALL)).toBe(true);
    expect(matchesPaymentFilter(rec({ membership_year: 2025 }), ALL)).toBe(true);
  });

  it("combineert met status: jaar 2025 + enkel openstaand laat een vereffend record vallen", () => {
    const betaald = rec({ membership_year: 2025, amount: "50.00", amount_paid: "50.00" });
    expect(matchesPaymentFilter(betaald, { status: "openstaand", context: "all", year: 2025 })).toBe(false);
    const open = rec({ membership_year: 2025, amount: "50.00", amount_paid: "10.00" });
    expect(matchesPaymentFilter(open, { status: "openstaand", context: "all", year: 2025 })).toBe(true);
  });
});

describe("matchesPaymentFilter — bestaande context/status blijven werken", () => {
  it("context=membership verbergt activiteit-inschrijvingen", () => {
    const activity = rec({ payable_type: "registration", membership_year: null, component_id: 3 });
    expect(matchesPaymentFilter(activity, { status: "all", context: "membership", year: null })).toBe(false);
    expect(matchesPaymentFilter(rec({}), { status: "all", context: "membership", year: null })).toBe(true);
  });

  it("context=comp-<id> matcht enkel dat onderdeel", () => {
    const c5 = rec({ payable_type: "registration", membership_year: null, component_id: 5 });
    const c9 = rec({ payable_type: "registration", membership_year: null, component_id: 9 });
    expect(matchesPaymentFilter(c5, { status: "all", context: "comp-5", year: null })).toBe(true);
    expect(matchesPaymentFilter(c9, { status: "all", context: "comp-5", year: null })).toBe(false);
  });

  it("status=paid/pending kijkt naar de status-badge; openstaand naar het saldo", () => {
    expect(matchesPaymentFilter(rec({ status: "paid" }), { status: "paid", context: "all", year: null })).toBe(true);
    expect(matchesPaymentFilter(rec({ status: "pending" }), { status: "paid", context: "all", year: null })).toBe(false);
  });
});

describe("saldoOf", () => {
  it("trekt betaald van te-betalen af", () => {
    expect(saldoOf(rec({ amount: "50.00", amount_paid: "20.00" }))).toBeCloseTo(30);
    expect(saldoOf(rec({ amount: "50.00", amount_paid: null }))).toBeCloseTo(50);
  });
});
