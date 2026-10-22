import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import i18n, { localeIntlTags, LOCALE_STORAGE_KEY, normalizeLocale, resolveInitialLocale, resources, setLocale, supportedLocales } from "./i18n";
import LanguageSelector from "./components/LanguageSelector";
import LocalizedUi, { translateOwnedText } from "./components/LocalizedUi";
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
  expect(normalizeLocale("de-DE")).toBe("de");
  expect(normalizeLocale("ru-RU")).toBe("ru");
  expect(normalizeLocale("es-MX")).toBe("es");
  expect(normalizeLocale("zh-CN")).toBe("zh-CN");
  expect(normalizeLocale("zh-Hans-CN")).toBe("zh-CN");
  expect(normalizeLocale("zh-TW")).toBeNull();
  expect(normalizeLocale("ja-JP")).toBe("ja");
  expect(normalizeLocale("fr-FR")).toBeNull();
});

test("locale resolution prefers a valid saved choice, then the first supported browser language", () => {
  expect(resolveInitialLocale({ getItem: () => "en" }, ["tr-TR"])).toBe("en");
  expect(resolveInitialLocale({ getItem: () => "de-DE" }, ["ru-RU"])).toBe("de");
  expect(resolveInitialLocale({ getItem: () => "invalid" }, ["fr-FR", "tr-TR", "en-US"])).toBe("tr");
  expect(resolveInitialLocale({ getItem: () => null }, ["fr-FR", "zh-CN", "ja-JP"])).toBe("zh-CN");
  expect(resolveInitialLocale({ getItem: () => null }, ["fr-FR"])).toBe("en");
});

test("English and Turkish resources have exactly the same grouped key set", () => {
  const paths = (value: object, prefix = ""): string[] => Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof child === "string" ? [path] : paths(child, path);
  });
  expect(paths(resources.tr.translation).sort()).toEqual(paths(resources.en.translation).sort());
  expect(Object.keys(resources)).toEqual(supportedLocales);
  expect(Object.keys(resources.en.translation)).toEqual(["common", "upload", "dashboard", "products", "customers", "errors"]);
  for (const locale of supportedLocales) {
    expect(paths(resources[locale].translation).sort()).toEqual(paths(resources.en.translation).sort());
  }
});

test("every added language immediately localizes dynamic UI, formatting and expiry plurals", async () => {
  const samples = {
    de: { overview: "Übersicht", plural: "Läuft in 2 Tagen ab", period: "1. Jan. 2025 bis 31. Dez. 2025", chart: "Gewichteter Stückpreis pro Tag von 1. Jan. 2025 bis 31. Dez. 2025" },
    ru: { overview: "Обзор", plural: "Истекает через 5 дней", period: "1 янв. 2025 г. — 31 дек. 2025 г.", chart: "Средневзвешенная цена за день с 1 янв. 2025 г. по 31 дек. 2025 г." },
    es: { overview: "Resumen", plural: "Caduca en 2 días", period: "1 ene 2025 a 31 dic 2025", chart: "Precio unitario ponderado por día de 1 ene 2025 a 31 dic 2025" },
    "zh-CN": { overview: "概览", plural: "将在 2 天后过期", period: "2025年1月1日 至 2025年12月31日", chart: "2025年1月1日 至 2025年12月31日 每天加权单价" },
    ja: { overview: "概要", plural: "2日後に期限切れ", period: "2025年1月1日～2025年12月31日", chart: "2025年1月1日～2025年12月31日の日あたり加重平均単価" },
  } as const;
  for (const locale of ["de", "ru", "es", "zh-CN", "ja"] as const) {
    await setLocale(locale);
    expect(document.documentElement.lang).toBe(locale);
    expect(i18n.t("common.overview")).toBe(samples[locale].overview);
    const daysAhead = locale === "ru" ? "2026-10-05T00:00:00Z" : "2026-10-02T00:00:00Z";
    expect(formatRelativeExpiry(daysAhead, new Date("2026-09-30T00:00:00Z"))).toBe(samples[locale].plural);
    expect(translateOwnedText("Weighted unit price per day from 2025-01-01 to 2025-12-31")).toBe(samples[locale].chart);
    expect(translateOwnedText("2025-01-01 to 2025-12-31")).toBe(samples[locale].period);
    expect(formatMoney("1234.5000", "USD")).toBe(new Intl.NumberFormat(localeIntlTags[locale], { style: "currency", currency: "USD" }).format(1234.5));
    expect(formatShare("0.125000")).toBe(new Intl.NumberFormat(localeIntlTags[locale], { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(0.125));
    expect(formatExpiry("2026-09-30T12:19:11Z", "Europe/Istanbul")).toBe(new Intl.DateTimeFormat(localeIntlTags[locale], { timeZone: "Europe/Istanbul", year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZoneName: "short" }).format(new Date("2026-09-30T12:19:11Z")));
  }
});

test("known backend reasons localize in every added language and retain safe unknown fallback", async () => {
  const expected = {
    de: "Für order_id ist ein Wert erforderlich.",
    ru: "Для order_id требуется значение.",
    es: "Se requiere un valor para order_id.",
    "zh-CN": "order_id 必须有值。",
    ja: "order_id の値は必須です。",
  } as const;
  for (const locale of Object.keys(expected) as (keyof typeof expected)[]) {
    await setLocale(locale);
    expect(localizedServerText("missing_value", { field: "order_id" }, "A value is required for order_id.")).toBe(expected[locale]);
    expect(localizedServerText("unknown.future_code", undefined, "Unknown server reason")).toBe("Unknown server reason");
  }
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
  expect(formatShare("0.125000")).toBe("%12,50");
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
