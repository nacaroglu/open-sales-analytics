import { expect, test } from "vitest";
import { formatCount, formatDay, formatExpiry, formatMonthYear, formatMoney, formatRelativeExpiry } from "./format";

test("money is shown with the currency symbol, thousands separators and two decimals", () => {
  expect(formatMoney("1234.5000", "USD")).toBe("$1,234.50");
  expect(formatMoney("0.0000", "USD")).toBe("$0.00");
});

test("money is rounded to the currency's minor units", () => {
  expect(formatMoney("1234.5678", "USD")).toBe("$1,234.57");
  expect(formatMoney("1.0050", "USD")).toBe("$1.01");
});

test("a currency without minor units has no decimals", () => {
  expect(formatMoney("1234.0000", "JPY")).toBe("¥1,234");
});

test("a very long value keeps every digit", () => {
  expect(formatMoney("1234567890.1200", "USD")).toBe("$1,234,567,890.12");
});

test("other currencies use their symbol with the en-US grouping", () => {
  expect(formatMoney("1234.5000", "EUR")).toBe("€1,234.50");
  expect(formatMoney("1234.5000", "GBP")).toBe("£1,234.50");
});

test("an invalid currency code falls back to the plain value with the code", () => {
  expect(formatMoney("12.5000", "not a code")).toBe("12.5000 not a code");
});

test("counts are whole numbers with thousands separators", () => {
  expect(formatCount(10482)).toBe("10,482");
  expect(formatCount(0)).toBe("0");
});

// ---- Dates (#42): fixed English text, independent of the browser's locale and zone ----

test("the expiry reads the same in Istanbul and New York apart from the zone's own clock", () => {
  const utc = "2026-09-30T12:19:11Z";
  expect(formatExpiry(utc, "Europe/Istanbul")).toBe("30 Sep 2026, 15:19 GMT+3");
  expect(formatExpiry(utc, "America/New_York")).toBe("30 Sep 2026, 08:19 EDT");
  expect(formatExpiry(utc, "UTC")).toBe("30 Sep 2026, 12:19 UTC");
});

test("month names are English, never Turkish", () => {
  for (const [utc, month] of [
    ["2026-01-15T10:00:00Z", "Jan"],
    ["2026-04-15T10:00:00Z", "Apr"],
    ["2026-08-15T10:00:00Z", "Aug"],
    ["2026-10-15T10:00:00Z", "Oct"],
  ]) {
    expect(formatExpiry(utc, "Europe/Istanbul")).toContain(` ${month} `);
  }
});

test("September is always Sep, and chart dates read the same in any zone", () => {
  const date = new Date("2025-09-05T00:00:00Z");
  expect(formatDay(date, false)).toBe("5 Sep");
  expect(formatDay(date, true)).toBe("5 Sep 2025");
  expect(formatMonthYear(date)).toBe("Sep 2025");
  expect(formatExpiry("2026-09-30T12:19:11Z", "UTC")).toContain("30 Sep 2026");
});

test("an unreadable expiry is returned as received", () => {
  expect(formatExpiry("soon")).toBe("soon");
  expect(formatRelativeExpiry("soon", new Date("2026-09-30T00:00:00Z"))).toBe("soon");
});

test("relative expiry uses whole units rounded down, with singular forms", () => {
  const expires = "2026-10-01T00:00:00Z";
  const at = (iso: string) => formatRelativeExpiry(expires, new Date(iso));
  expect(at("2026-09-30T00:00:30Z")).toBe("Expires in 23 hours");
  expect(at("2026-09-30T22:59:00Z")).toBe("Expires in 1 hour");
  expect(at("2026-09-30T23:01:00Z")).toBe("Expires in 59 minutes");
  expect(at("2026-09-30T23:59:00Z")).toBe("Expires in 1 minute");
  expect(at("2026-09-30T23:59:30Z")).toBe("Expires in less than a minute");
  expect(at("2026-10-01T00:00:00Z")).toBe("Expires in less than a minute");
  expect(at("2026-09-30T00:00:00Z")).toBe("Expires in 1 day");
  expect(at("2026-09-28T00:00:00Z")).toBe("Expires in 3 days");
});
