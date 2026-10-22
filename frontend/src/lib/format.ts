import i18n, { normalizeLocale } from "../i18n";

function locale(): "en-US" | "tr-TR" {
  return normalizeLocale(i18n.resolvedLanguage) === "tr" ? "tr-TR" : "en-US";
}

const moneyFormats = new Map<string, Intl.NumberFormat>();

function moneyFormat(currency: string): Intl.NumberFormat {
  const key = `${locale()}:${currency}`;
  let format = moneyFormats.get(key);
  if (format === undefined) {
    // The currency's own minor units decide the decimals: two for USD, none for JPY.
    format = new Intl.NumberFormat(locale(), { style: "currency", currency });
    moneyFormats.set(key, format);
  }
  return format;
}

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
  return new Intl.NumberFormat(locale(), { maximumFractionDigits: 0 }).format(value);
}

export function formatShare(value: string): string {
  const [whole, fraction = ""] = value.split(".");
  const digits = `${fraction}000000`.slice(0, 6);
  const scaled = BigInt(whole || "0") * 10000n + BigInt(digits);
  const rounded = (scaled + 50n) / 100n;
  const text = rounded.toString().padStart(3, "0");
  const decimal = locale() === "tr-TR" ? "," : ".";
  return `${text.slice(0, -2)}${decimal}${text.slice(-2)}%`;
}

export function formatPercent(value: number, fractionDigits: number = 1): string {
  return new Intl.NumberFormat(locale(), {
    style: "percent",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

// Application-generated dates are English in every browser. The locale is fixed
// and never taken from the browser, so a Turkish browser gets the same text. The
// parts come from en-US and are put together day first here, because en-GB's own
// month names differ between engines ("Sep" or "Sept").
function parts(date: Date, options: Intl.DateTimeFormatOptions): Record<string, string> {
  const found: Record<string, string> = {};
  for (const part of new Intl.DateTimeFormat(locale(), options).formatToParts(date)) {
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

// Relative copy comes from the locale resource and uses i18next plural forms.
// `now` is a parameter so a test can fix it. An unreadable instant is returned as is.
export function formatRelativeExpiry(utc: string, now: Date): string {
  const expires = new Date(utc);
  if (Number.isNaN(expires.getTime())) return utc;
  const minutes = Math.floor((expires.getTime() - now.getTime()) / 60_000);
  if (minutes < 1) return i18n.t("common.extra.expiresInLessMinute");
  if (minutes < 60) return i18n.t("common.extra.expiresMinute", { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return i18n.t("common.extra.expiresHour", { count: hours });
  return i18n.t("common.extra.expiresDay", { count: Math.floor(hours / 24) });
}
