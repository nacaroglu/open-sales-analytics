import { describe, expect, test } from "vitest";
import { lowCoverageExplanation, lowCoverageOrders, suppressedExplanation, suppressedOrders, unavailableExplanation } from "./customerCopy";

describe("customer coverage copy", () => {
  test("uses integer math for the warning threshold", () => {
    expect(lowCoverageOrders(10_000, 7_000)).toBe(1_000);
    expect(lowCoverageOrders(9, 5)).toBe(3);
    expect(lowCoverageExplanation(0.7, 7_000, 10_000)).toContain("Add a customer_id to 1,000 more identified orders to reach 80%.");
  });

  test("uses integer math for the suppressed threshold", () => {
    expect(suppressedOrders(9, 4)).toBe(1);
    expect(suppressedOrders(10, 0)).toBe(5);
    expect(suppressedExplanation(0, 0, 10, true)).toContain("customer_id column is present but empty");
  });

  test("keeps unavailable guidance privacy-safe", () => {
    expect(unavailableExplanation).toContain("Overview and Products work without it.");
    expect(unavailableExplanation).not.toMatch(/revenue|anonymous|anonymised/i);
  });
});
