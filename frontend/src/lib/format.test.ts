import { expect, test } from "vitest";
import { formatCount, formatMoney } from "./format";

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
