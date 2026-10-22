export const CUSTOMER_COVERAGE_WARNING = 50;
export const CUSTOMER_COVERAGE_NORMAL = 80;

export function truncatedCoverage(value: number | null): string {
  return value === null ? "—" : formatPercent(Math.floor(value * 1000) / 1000, 1);
}

export function lowCoverageOrders(total: number, identified: number): number {
  return Math.max(0, Math.ceil(total * CUSTOMER_COVERAGE_NORMAL / 100) - identified);
}

export function suppressedOrders(total: number, identified: number): number {
  return Math.max(0, Math.ceil(total * CUSTOMER_COVERAGE_WARNING / 100) - identified);
}

export function lowCoverageExplanation(coverage: number, identified: number, total: number): string {
  if (normalizeLocale(i18n.resolvedLanguage) === "tr") {
    return `Siparişlerin yalnızca ${truncatedCoverage(coverage)} kadarında (${formatCount(identified)}/${formatCount(total)}) müşteri kimliği var. Müşteri göstergeleri yalnızca bu siparişleri açıklar. Kimliği olmayan müşteriler farklı alışveriş yapabileceğinden elde tutma, tekrar satın alma ve değer gösterilenden daha yüksek veya düşük olabilir. %80'e ulaşmak için ${formatCount(lowCoverageOrders(total, identified))} siparişe daha customer_id ekleyin.`;
  }
  return `Only ${truncatedCoverage(coverage)} of orders (${formatCount(identified)} of ${formatCount(total)}) have a customer ID. Customer figures describe those orders only. Customers without an ID may buy differently, so retention, repeat purchase and value can be higher or lower than shown. Add a customer_id to ${formatCount(lowCoverageOrders(total, identified))} more identified orders to reach 80%.`;
}

export function suppressedExplanation(coverage: number | null, identified: number, total: number, hasColumn: boolean): string {
  if (normalizeLocale(i18n.resolvedLanguage) === "tr") {
    const prefix = hasColumn && identified === 0
      ? "customer_id sütunu var ancak boş."
      : `Müşteri analizi için siparişlerin en az %50'sinde müşteri kimliği gerekir. Bu dosyada oran ${truncatedCoverage(coverage)} (${formatCount(identified)}/${formatCount(total)} sipariş).`;
    return `${prefix} Analizi açmak için ${formatCount(suppressedOrders(total, identified))} siparişe daha customer_id ekleyin; %80 ve üzeri düşük kapsam uyarısını kaldırır. Genel bakış ve Ürünler etkilenmez.`;
  }
  const prefix = hasColumn && identified === 0
    ? "The customer_id column is present but empty."
    : `Customer analytics needs a customer ID on at least 50% of orders. This file has ${truncatedCoverage(coverage)} (${formatCount(identified)} of ${formatCount(total)} orders).`;
  return `${prefix} Add a customer_id to ${formatCount(suppressedOrders(total, identified))} more orders to unlock it; 80% or more removes the low-coverage warning. Overview and Products are unaffected.`;
}

export function unavailableExplanation(): string {
  if (normalizeLocale(i18n.resolvedLanguage) === "tr") {
    return "Bu dosyada customer_id sütunu olmadığı için müşteri analizi kullanılamıyor. Genel bakış ve Ürünler bu sütun olmadan çalışır. Analizi açmak için karma kimlik, UUID veya dahili müşteri anahtarı gibi anonim bir değer içeren isteğe bağlı customer_id sütunu ekleyin. E-posta adresi, telefon numarası veya ad kullanmayın. Boş değerlere izin verilir; bir siparişin tüm satırlarında aynı müşteri kimliği bulunmalıdır. Veri kümesi değiştirilemediği için dosyanın yeniden yüklenmesi gerekir.";
  }
  return "This file has no customer_id column, so customer analytics is unavailable. Overview and Products work without it. To unlock it, add an optional customer_id column with an opaque value such as a hashed ID, a UUID or an internal customer key. Do not use email addresses, phone numbers or names. Blanks are allowed; all rows of one order must have the same customer ID. The file must be uploaded again because a dataset cannot be changed.";
}
import i18n, { normalizeLocale } from "../i18n";
import { formatCount, formatPercent } from "./format";
