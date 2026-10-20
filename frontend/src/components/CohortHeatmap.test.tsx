import { afterEach, expect, test } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import CohortHeatmap, { retentionShade } from "./CohortHeatmap";

afterEach(cleanup);

test.each([
  [0, "bg-white"],
  [0.0999, "bg-indigo-50"],
  [0.1, "bg-indigo-100"],
  [0.25, "bg-indigo-200"],
  [0.5, "bg-indigo-300"],
  [0.75, "bg-indigo-400"],
  [1, "bg-indigo-400"],
])("retention %s is shaded %s", (retention, shade) => {
  expect(retentionShade(retention)).toBe(shade);
});

test("cells are shaded by retention and keep the percentage, count and maturity as text", () => {
  render(
    <CohortHeatmap
      rows={[
        {
          cohort_month: "2025-01",
          cohort_size: 4,
          complete_months: 2,
          cells: [
            { month_offset: 0, state: "complete", retained_count: 4, retention: 1 },
            { month_offset: 1, state: "complete", retained_count: 1, retention: 0.25 },
            { month_offset: 2, state: "partial", retained_count: 0, retention: 0 },
            { month_offset: 3, state: "not_observed", retained_count: null, retention: null },
          ],
        },
      ]}
    />,
  );

  const table = screen.getByRole("table", { name: "Cohort retention table" });
  const cells = within(within(table).getAllByRole("row")[1]).getAllByRole("cell");
  expect(cells.map((cell) => cell.textContent)).toEqual(["2025-01", "4", "2", "100.0% (4)", "25.0% (1)", "0.0% (0)partial", "Not yet observed"]);
  expect(cells[3]).toHaveClass("bg-indigo-400");
  expect(cells[4]).toHaveClass("bg-indigo-200");
  expect(cells[5]).toHaveClass("bg-white");
  expect(cells[6]).toHaveClass("border-dashed");
  expect(within(table).getByRole("columnheader", { name: "Month 3" })).toBeInTheDocument();
  const key = screen.getByRole("group", { name: "Retention shading key" });
  expect(key).toHaveTextContent("0%Under 10%10–25%25–50%50–75%75% and overNot yet observed");
});
