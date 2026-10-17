import { expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import ComparisonDates from "./ComparisonDates";

test("renders exact API dates and comparison mode", () => {
  render(<ComparisonDates comparison={{ mode: "previous_year", current: { start: "2024-02-01", end: "2024-02-29" }, comparison: { start: "2023-02-01", end: "2023-02-28" }, state: "available", reason: null }} />);
  expect(screen.getByText("2024-02-01 to 2024-02-29 compared with 2023-02-01 to 2023-02-28 (same period last year)")).toBeInTheDocument();
});

test("shows unavailable state and reason without inventing dates", () => {
  render(<ComparisonDates comparison={{ mode: "previous_period", current: { start: "2025-03-10", end: "2025-03-10" }, comparison: { start: "2025-03-09", end: "2025-03-09" }, state: "insufficient_data", reason: "The comparison needs earlier data." }} />);
  expect(screen.getByText("Comparison unavailable", { exact: false })).toBeInTheDocument();
  expect(screen.getByText(/The comparison needs earlier data/)).toBeInTheDocument();
});
