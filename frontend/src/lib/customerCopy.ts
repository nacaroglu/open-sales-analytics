export const CUSTOMER_COVERAGE_WARNING = 50;
export const CUSTOMER_COVERAGE_NORMAL = 80;

export function truncatedCoverage(value: number | null): string {
  return value === null ? "—" : `${Math.floor(value * 1000) / 10}%`;
}

export function lowCoverageOrders(total: number, identified: number): number {
  return Math.max(0, Math.ceil(total * CUSTOMER_COVERAGE_NORMAL / 100) - identified);
}

export function suppressedOrders(total: number, identified: number): number {
  return Math.max(0, Math.ceil(total * CUSTOMER_COVERAGE_WARNING / 100) - identified);
}

export function lowCoverageExplanation(coverage: number, identified: number, total: number): string {
  return `Only ${truncatedCoverage(coverage)} of orders (${identified.toLocaleString("en-US")} of ${total.toLocaleString("en-US")}) have a customer ID. Customer figures describe those orders only. Customers without an ID may buy differently, so retention, repeat purchase and value can be higher or lower than shown. Add a customer_id to ${lowCoverageOrders(total, identified).toLocaleString("en-US")} more identified orders to reach 80%.`;
}

export function suppressedExplanation(coverage: number | null, identified: number, total: number, hasColumn: boolean): string {
  const prefix = hasColumn && identified === 0
    ? "The customer_id column is present but empty."
    : `Customer analytics needs a customer ID on at least 50% of orders. This file has ${truncatedCoverage(coverage)} (${identified.toLocaleString("en-US")} of ${total.toLocaleString("en-US")} orders).`;
  return `${prefix} Add a customer_id to ${suppressedOrders(total, identified).toLocaleString("en-US")} more orders to unlock it; 80% or more removes the low-coverage warning. Overview and Products are unaffected.`;
}

export const unavailableExplanation = "This file has no customer_id column, so customer analytics is unavailable. Overview and Products work without it. To unlock it, add an optional customer_id column with an opaque value such as a hashed ID, a UUID or an internal customer key. Do not use email addresses, phone numbers or names. Blanks are allowed; all rows of one order must have the same customer ID. The file must be uploaded again because a dataset cannot be changed.";
