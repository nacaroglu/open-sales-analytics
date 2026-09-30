// Number formatting shared by the KPI cards, the trend chart and the top
// products table. The locale is fixed to en-US so the output does not depend on
// the browser's settings.

const LOCALE = "en-US";

const moneyFormats = new Map<string, Intl.NumberFormat>();

function moneyFormat(currency: string): Intl.NumberFormat {
  let format = moneyFormats.get(currency);
  if (format === undefined) {
    // The currency's own minor units decide the decimals: two for USD, none for JPY.
    format = new Intl.NumberFormat(LOCALE, { style: "currency", currency });
    moneyFormats.set(currency, format);
  }
  return format;
}

const wholeNumbers = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

// The server sends money as a string with 4 decimals. The string goes to Intl
// as is, so it is rounded from its exact decimal value, not from a float.
export function formatMoney(value: string, currency: string): string {
  try {
    // Intl reads the decimal string exactly (older engines fall back to a number).
    return moneyFormat(currency).format(value as unknown as number);
  } catch {
    // An unknown currency code: show the plain value with the code, never nothing.
    return `${value} ${currency}`;
  }
}

export function formatCount(value: number): string {
  return wholeNumbers.format(value);
}
