import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import i18n, { LOCALE_STORAGE_KEY, normalizeLocale, resolveInitialLocale, resources, setLocale } from "./i18n";
import LanguageSelector from "./components/LanguageSelector";
import LocalizedUi from "./components/LocalizedUi";
import { formatCount, formatExpiry, formatMoney, formatRelativeExpiry, formatShare } from "./lib/format";
import { localizedServerText } from "./lib/localizedCopy";

afterEach(async () => {
  cleanup();
  localStorage.clear();
  await setLocale("en");
});

test("normalizes supported regional tags and rejects unavailable locales", () => {
  expect(normalizeLocale("tr-TR")).toBe("tr");
  expect(normalizeLocale("EN-gb")).toBe("en");
  expect(normalizeLocale("de-DE")).toBeNull();
});

test("locale resolution prefers a valid saved choice, then the first supported browser language", () => {
  expect(resolveInitialLocale({ getItem: () => "en" }, ["tr-TR"])).toBe("en");
  expect(resolveInitialLocale({ getItem: () => "invalid" }, ["de-DE", "tr-TR", "en-US"])).toBe("tr");
  expect(resolveInitialLocale({ getItem: () => null }, ["de-DE"])).toBe("en");
});

test("English and Turkish resources have exactly the same grouped key set", () => {
  const paths = (value: object, prefix = ""): string[] => Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof child === "string" ? [path] : paths(child, path);
  });
  expect(paths(resources.tr.translation).sort()).toEqual(paths(resources.en.translation).sort());
  expect(Object.keys(resources.en.translation)).toEqual(["common", "upload", "dashboard", "products", "customers", "errors"]);
});

test("known server validation codes interpolate scalar values and unknown codes keep English fallback", async () => {
  await setLocale("tr");
  expect(localizedServerText("missing_value", { field: "order_id" }, "A value is required for order_id.")).toBe("order_id için değer zorunludur.");
  expect(localizedServerText("duplicate_column", { field: "order_id", count: 2 }, "The column 'order_id' appears 2 times.")).toBe("'order_id' sütunu 2 kez bulunuyor.");
  expect(localizedServerText("future.code", { field: "order_id" }, "Unknown server reason")).toBe("Unknown server reason");
});

test("the selector switches immediately, persists osa.locale and updates html lang", async () => {
  render(<LocalizedUi><LanguageSelector /><button>Retry</button></LocalizedUi>);
  fireEvent.change(screen.getByLabelText("Language"), { target: { value: "tr" } });
  await waitFor(() => expect(document.documentElement.lang).toBe("tr"));
  expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("tr");
  expect(screen.getByRole("button", { name: "Yeniden dene" })).toBeInTheDocument();
  expect(i18n.resolvedLanguage).toBe("tr");
  fireEvent.change(screen.getByLabelText("Dil"), { target: { value: "en" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument());
  expect(document.documentElement.lang).toBe("en");
});

test("Turkish formatting covers money, numbers, percentages, instants and relative expiry", async () => {
  await setLocale("tr");
  expect(formatMoney("1234.5000", "TRY")).toMatch(/1\.234,50/);
  expect(formatCount(1234)).toBe("1.234");
  expect(formatShare("0.125000")).toBe("12,50%");
  expect(formatExpiry("2026-09-30T12:19:11Z", "Europe/Istanbul")).toContain("30 Eyl 2026");
  expect(formatRelativeExpiry("2026-10-01T00:00:00Z", new Date("2026-09-30T00:00:00Z"))).toBe("1 gün içinde sona erer");
  expect(formatRelativeExpiry("2026-10-02T00:00:00Z", new Date("2026-09-30T00:00:00Z"))).toBe("2 gün içinde sona erer");
  expect(formatRelativeExpiry("2026-09-30T00:02:00Z", new Date("2026-09-30T00:00:00Z"))).toBe("2 dakika içinde sona erer");
});

test("English relative expiry uses singular and plural resource forms", async () => {
  await setLocale("en");
  const now = new Date("2026-09-30T00:00:00Z");
  expect(formatRelativeExpiry("2026-09-30T00:01:00Z", now)).toBe("Expires in 1 minute");
  expect(formatRelativeExpiry("2026-09-30T00:02:00Z", now)).toBe("Expires in 2 minutes");
});
