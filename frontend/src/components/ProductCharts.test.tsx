import { afterEach, expect, test } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { BucketLineChart, ParetoChart } from "./ProductCharts";

afterEach(cleanup);

const range = { start: "2025-03-01", end: "2025-03-31" };

test("Pareto: cumulative line over ranked products, dashed 80% reference line and a text key", () => {
  const { container } = render(
    <ParetoChart
      range={range}
      products={[
        { product_id: "a", product_name: "Mug", cumulative_share: "0.600000" },
        { product_id: "b", product_name: "Cup", cumulative_share: "0.900000" },
        { product_id: "c", product_name: "Plate", cumulative_share: "1.000000" },
      ]}
    />,
  );

  expect(
    screen.getByRole("img", {
      name: "Cumulative share of gross sales over 3 products ranked by gross sales, from 2025-03-01 to 2025-03-31",
    }),
  ).toBeInTheDocument();
  expect(container.querySelectorAll(".recharts-line-dots circle")).toHaveLength(3);
  const reference = container.querySelector(".recharts-reference-line line");
  expect(reference).toHaveAttribute("stroke-dasharray", "6 4");
  expect(reference).toHaveAttribute("stroke", "#432dd7");
  expect(screen.getByText("Products ranked by gross sales, left to right. Solid line: cumulative share of gross sales. Dashed line: 80% of gross sales.")).toBeInTheDocument();
});

test("Pareto: products without a share (zero total) are left out of the line", () => {
  render(<ParetoChart range={range} products={[{ product_id: "a", product_name: "Mug", cumulative_share: null }]} />);

  expect(screen.getByRole("img", { name: /over 0 products/ })).toBeInTheDocument();
});

test("bucket line: one point per value, a null is a gap and the table says so", () => {
  const { container } = render(
    <BucketLineChart
      points={[
        { bucket_start: "2025-03-01", value: "2.5000" },
        { bucket_start: "2025-03-02", value: null },
        { bucket_start: "2025-03-03", value: "3.0000" },
      ]}
      granularity="daily"
      range={range}
      currency="USD"
      seriesName="Average price per unit"
      label="Weighted unit price per day from 2025-03-01 to 2025-03-31"
    />,
  );

  expect(screen.getByRole("img", { name: "Weighted unit price per day from 2025-03-01 to 2025-03-31" })).toBeInTheDocument();
  expect(container.querySelectorAll(".recharts-line-dots circle")).toHaveLength(2);
  const rows = within(screen.getByRole("table")).getAllByRole("row").map((row) => row.textContent);
  expect(rows).toEqual(["PeriodAverage price per unit", "1 Mar 2025$2.50", "2 Mar 2025—", "3 Mar 2025$3.00"]);
});

test("bucket line: a partial month is hollow and the table shows its covered dates", () => {
  const { container } = render(
    <BucketLineChart
      points={[
        { bucket_start: "2025-02-01", value: "10.0000" },
        { bucket_start: "2025-03-01", value: "20.0000" },
      ]}
      granularity="monthly"
      range={{ start: "2025-02-10", end: "2025-03-31" }}
      currency="USD"
      seriesName="Gross sales"
      label="Gross sales per month"
    />,
  );

  const fills = Array.from(container.querySelectorAll(".recharts-line-dots circle")).map((dot) => dot.getAttribute("fill"));
  expect(fills).toEqual(["#ffffff", "#432dd7"]);
  expect(screen.getByRole("cell", { name: "10–28 Feb 2025" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "Mar 2025" })).toBeInTheDocument();
});
