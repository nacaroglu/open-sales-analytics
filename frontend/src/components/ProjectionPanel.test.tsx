import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import ProjectionPanel from "./ProjectionPanel";
import type { Projected12MonthCustomerValue } from "../lib/types";

const retry = vi.fn();

const eligible: Projected12MonthCustomerValue = {
  is_estimate: true,
  horizon_months: 12,
  data_cutoff: "2025-12-31",
  eligibility: {
    status: "eligible",
    data_cutoff: "2025-12-31",
    conditions: [
      { code: "history_months", label: "At least 18 months of history", actual: 23, threshold: 18, passed: true },
      { code: "identified_customers", label: "At least 500 identified customers", actual: 500, threshold: 500, passed: true },
      { code: "customer_coverage", label: "At least 70% customer coverage", actual: "0.7000", threshold: "0.70", passed: true },
      { code: "mature_cohorts", label: "At least 5 mature cohorts", actual: 8, threshold: 5, passed: true },
    ],
  },
  value: {
    customers: 500,
    contributing_mature_cohorts: 8,
    observed_per_customer: "42.1250",
    projected_per_customer_estimate: "17.8750",
    total_per_customer_estimate: "60.0000",
    cohorts: [
      {
        cohort_month: "2025-01",
        customers: 60,
        observed_age_months: 12,
        mature: true,
        observed_per_customer: "50.0000",
        projected_per_customer_estimate: "0.0000",
        total_per_customer_estimate: "50.0000",
      },
    ],
  },
};

afterEach(() => {
  cleanup();
  retry.mockReset();
});

function renderPanel(projection: Projected12MonthCustomerValue | undefined, props: Partial<React.ComponentProps<typeof ProjectionPanel>> = {}) {
  return render(<ProjectionPanel projection={projection} currency="USD" onRetry={retry} {...props} />);
}

describe("ProjectionPanel", () => {
  test("renders eligible figures, cutoff, cohort count and the table", () => {
    renderPanel(eligible);
    const section = screen.getByRole("region", { name: "Projected 12-Month Customer Value" });

    expect(within(section).getByRole("heading", { level: 2, name: "Projected 12-Month Customer Value" })).toBeInTheDocument();
    expect(within(section).getByText("Estimate")).toBeInTheDocument();
    expect(within(section).getByText("12-month horizon")).toBeInTheDocument();
    expect(within(section).getByText("Observed so far").parentElement).toHaveTextContent("$42.13");
    expect(within(section).getByText("Projected (estimate)", { selector: "dt" }).parentElement).toHaveTextContent("$17.88");
    expect(within(section).getByText("12-month total (estimate)", { selector: "dt" }).parentElement).toHaveTextContent("$60.00");
    expect(within(section).getByText("Data up to 2025-12-31 · based on 8 mature cohorts · 500 customers")).toBeInTheDocument();
    expect(within(section).getByText(/Estimate of average gross sales per customer/)).toBeInTheDocument();
    expect(within(section).getByRole("table", { name: "Projected 12-Month Customer Value table" })).toHaveTextContent("Jan 2025");
    expect(within(section).getByRole("columnheader", { name: "Projected (estimate)" })).toBeInTheDocument();
    expect(within(section).getByRole("cell", { name: "$0.00" })).toBeInTheDocument();
    expect(section.textContent).not.toMatch(/revenue|profit|lifetime|LTV|guaranteed|will earn/i);
  });

  test("renders ineligible conditions first and does not render money", () => {
    renderPanel({
      ...eligible,
      eligibility: {
        ...eligible.eligibility,
        status: "ineligible",
        conditions: eligible.eligibility.conditions.map((condition, index) => ({ ...condition, actual: index === 1 ? 0 : condition.actual, passed: index === 0 })),
      },
      value: null,
    });
    const section = screen.getByRole("region", { name: "Projected 12-Month Customer Value" });
    expect(within(section).getByRole("heading", { name: "Not enough data for a reliable estimate" })).toBeInTheDocument();
    expect(within(section).getByText("At least 500 identified customers")).toBeInTheDocument();
    expect(within(section).getByText(/this dataset: 0/)).toBeInTheDocument();
    expect(within(section).getAllByText("Not met")).toHaveLength(3);
    expect(within(section).queryByText(/\$|€/)).not.toBeInTheDocument();
    expect(within(section).getByText("At least 500 identified customers").parentElement?.parentElement?.textContent).toMatch(/Not met/);
  });

  test("renders unavailable guidance and coverage as a percentage", () => {
    renderPanel({
      ...eligible,
      eligibility: {
        ...eligible.eligibility,
        status: "unavailable",
        conditions: eligible.eligibility.conditions.map((condition) => condition.code === "customer_coverage" ? { ...condition, actual: "0.6999", passed: false } : { ...condition, actual: null, passed: false }),
      },
      value: null,
    });
    const section = screen.getByRole("region", { name: "Projected 12-Month Customer Value" });
    expect(within(section).getByText("Add a customer_id column to your file to see this estimate.")).toBeInTheDocument();
    expect(within(section).getByText(/this dataset: 69\.99%/)).toBeInTheDocument();
    expect((section.textContent?.match(/not available/g) ?? []).length).toBe(3);
  });

  test("shows loading and error states with retry", () => {
    renderPanel(undefined, { loading: true });
    expect(screen.getByRole("status", { name: "Projected 12-Month Customer Value" })).toHaveAttribute("aria-busy", "true");
    cleanup();

    renderPanel(undefined, { loading: false, error: true });
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong loading this data");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
