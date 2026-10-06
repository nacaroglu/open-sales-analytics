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

// Application-generated dates are English in every browser. The locale is fixed
// and never taken from the browser, so a Turkish browser gets the same text. The
// parts come from en-US and are put together day first here, because en-GB's own
// month names differ between engines ("Sep" or "Sept").
const DATE_LOCALE = "en-US";

function parts(date: Date, options: Intl.DateTimeFormatOptions): Record<string, string> {
  const found: Record<string, string> = {};
  for (const part of new Intl.DateTimeFormat(DATE_LOCALE, options).formatToParts(date)) {
    found[part.type] = part.value;
  }
  return found;
}

// "5 Mar" or "5 Mar 2025" from a UTC date (calendar dates are read as UTC, so the
// browser's zone never moves them).
export function formatDay(date: Date, withYear: boolean): string {
  const p = parts(date, { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" });
  return `${p.day} ${p.month}${withYear ? ` ${p.year}` : ""}`;
}

// "Mar 2025" from a UTC date.
export function formatMonthYear(date: Date): string {
  const p = parts(date, { timeZone: "UTC", month: "short", year: "numeric" });
  return `${p.month} ${p.year}`;
}

// The expiry is a UTC instant, shown in the browser's local time zone (or in
// `timeZone` when given, which tests use): "30 Sep 2026, 08:19 EDT". Calendar
// dates are never passed here: they are shown exactly as received.
export function formatExpiry(utc: string, timeZone?: string): string {
  const date = new Date(utc);
  if (Number.isNaN(date.getTime())) return utc;
  const p = parts(date, {
    timeZone,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZoneName: "short",
  });
  return `${p.day} ${p.month} ${p.year}, ${p.hour}:${p.minute} ${p.timeZoneName}`;
}

function plural(count: number, unit: string): string {
  return `${count} ${unit}${count === 1 ? "" : "s"}`;
}

// "Expires in 23 hours": whole units, rounded down, in English. `now` is a
// parameter so a test can fix it. An unreadable instant is returned as is.
export function formatRelativeExpiry(utc: string, now: Date): string {
  const expires = new Date(utc);
  if (Number.isNaN(expires.getTime())) return utc;
  const minutes = Math.floor((expires.getTime() - now.getTime()) / 60_000);
  if (minutes < 1) return "Expires in less than a minute";
  if (minutes < 60) return `Expires in ${plural(minutes, "minute")}`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Expires in ${plural(hours, "hour")}`;
  return `Expires in ${plural(Math.floor(hours / 24), "day")}`;
}
