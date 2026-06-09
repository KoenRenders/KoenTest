/**
 * Parse a price string from the API into a number for display only.
 * Never use this result for financial calculations — always keep prices
 * as strings and do arithmetic server-side.
 */
export function parsePrice(value: string | undefined | null): number {
  if (!value) return 0;
  return parseFloat(value);
}

export function formatPrice(value: string | undefined | null): string {
  return `€${parsePrice(value).toFixed(2)}`;
}

export function isPositivePrice(value: string | undefined | null): boolean {
  return parsePrice(value) > 0;
}
