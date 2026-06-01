/**
 * Currency formatting utilities.
 * Maps ISO 4217 currency codes to their display symbols.
 * Never converts between currencies — native amounts are always preserved.
 */

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$",
  ILS: "₪",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
  CAD: "CA$",
  AUD: "A$",
  CHF: "CHF ",
  SEK: "kr",
  NOK: "kr",
  DKK: "kr",
  NZD: "NZ$",
  SGD: "S$",
  HKD: "HK$",
  INR: "₹",
  BRL: "R$",
  MXN: "MX$",
};

/**
 * Format an amount with its native currency symbol.
 * Returns e.g. "$12.90", "₪12.90", "€9.99".
 * Unknown currencies are prefixed with the code and a space: "XYZ 5.00".
 *
 * Does NOT convert between currencies. ILS amounts are always shown in ₪.
 */
export function formatCurrency(amount: number, currency: string | null | undefined): string {
  const code = (currency ?? "USD").toUpperCase();
  const sym = CURRENCY_SYMBOLS[code] ?? `${code} `;
  return `${sym}${amount.toFixed(2)}`;
}

/**
 * Format a monthly-equivalent amount.
 * Returns e.g. "₪12.90/mo" or "$9.99/mo".
 */
export function formatMonthly(amount: number, currency: string | null | undefined): string {
  return `${formatCurrency(amount, currency)}/mo`;
}

/**
 * Format a UTC ISO date/datetime string in the browser's local timezone.
 * Returns e.g. "Jan 15, 2026". Returns "—" for null/empty input.
 * DB values are always UTC; this converts to local time for display only.
 */
export function formatDateLocal(utcString: string | null | undefined): string {
  if (!utcString) return "—";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(utcString));
}
