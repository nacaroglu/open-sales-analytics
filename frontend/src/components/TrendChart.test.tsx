import { afterEach, beforeAll, expect, test } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import TrendChart, {
  bucketLabel,
  bucketLabelWithYear,
  formatMoneyShort,
  parseBucketDate,
  rangeSentence,
} from "./TrendChart";

afterEach(cleanup);

beforeAll(() => {
  // Node re-reads TZ when it is assigned: a zone west of UTC would shift a
  // local-time date back a day, a UTC-based label must not move.
  (globalThis as unknown as { process: { env: Record<string, string> } }).process.env.TZ =
    "America/Los_Angeles";
});

const range = { start: "2025-03-01", end: "2025-03-31" };

// X-axis tick texts. Recharts leaves a hidden measuring span in the body, so
// getByText would match it too: read the ticks from the axis instead.
function xLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll(".recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-value")).map(
    (el) => el.textContent ?? "",
  );
}

function renderChart(
  granularity: "daily" | "weekly" | "monthly",
  buckets: { bucket_start: string; gross_sales: string }[],
  currency = "USD",
) {
  return render(
    <TrendChart granularity={granularity} buckets={buckets} range={range} currency={currency} />,
  );
}

test("daily: heading, range sentence, text alternative and an axis label", () => {
  const { container } = renderChart("daily", [
    { bucket_start: "2025-03-01", gross_sales: "100.0000" },
    { bucket_start: "2025-03-02", gross_sales: "250.5000" },
    { bucket_start: "2025-03-03", gross_sales: "0.0000" },
  ]);

  expect(screen.getByRole("heading", { level: 2, name: "Gross sales — daily" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Daily gross sales from 2025-03-01 to 2025-03-31" })).toBeInTheDocument();
  expect(screen.getByText("Daily gross sales from 2025-03-01 to 2025-03-31")).toBeInTheDocument();
  expect(xLabels(container)).toEqual(["1 Mar", "2 Mar", "3 Mar"]);
});

test("weekly: heading and a Week of label, the first bucket may start before the range", () => {
  const { container } = renderChart("weekly", [
    { bucket_start: "2025-02-24", gross_sales: "10.0000" },
    { bucket_start: "2025-03-03", gross_sales: "20.0000" },
  ]);

  expect(screen.getByRole("heading", { name: "Gross sales — weekly" })).toBeInTheDocument();
  expect(xLabels(container)).toEqual(["Week of 24 Feb", "Week of 3 Mar"]);
  expect(screen.getByRole("img")).toHaveAttribute(
    "aria-label",
    "Weekly gross sales from 2025-03-01 to 2025-03-31",
  );
});

test("monthly: heading and a month with year label", () => {
  const { container } = renderChart("monthly", [
    { bucket_start: "2025-03-01", gross_sales: "10.0000" },
    { bucket_start: "2025-04-01", gross_sales: "20.0000" },
  ]);

  expect(screen.getByRole("heading", { name: "Gross sales — monthly" })).toBeInTheDocument();
  expect(xLabels(container)).toEqual(["Mar 2025", "Apr 2025"]);
});

test("a single bucket still draws the chart with its label and a point", () => {
  const { container } = renderChart("daily", [{ bucket_start: "2025-03-05", gross_sales: "42.0000" }]);

  expect(xLabels(container)).toEqual(["5 Mar"]);
  expect(screen.queryByText("No sales in this range")).not.toBeInTheDocument();
  expect(container.querySelector(".recharts-line-dots circle")).not.toBeNull();
});

test("a zero bucket between sales is kept, not skipped", () => {
  const { container } = renderChart("daily", [
    { bucket_start: "2025-03-01", gross_sales: "5.0000" },
    { bucket_start: "2025-03-02", gross_sales: "0.0000" },
    { bucket_start: "2025-03-03", gross_sales: "5.0000" },
  ]);

  expect(container.querySelectorAll(".recharts-line-dots circle")).toHaveLength(3);
});

test("every bucket zero shows the empty message instead of a flat line", () => {
  const { container } = renderChart("weekly", [
    { bucket_start: "2025-03-03", gross_sales: "0.0000" },
    { bucket_start: "2025-03-10", gross_sales: "0.0000" },
  ]);

  const message = screen.getByText("No sales in this range");
  expect(message).toHaveClass("h-72", "flex", "items-center", "justify-center");
  expect(screen.getByRole("heading", { name: "Gross sales — weekly" })).toBeInTheDocument();
  expect(container.querySelector("svg")).toBeNull();
});

test("an empty trend also shows the empty message", () => {
  renderChart("daily", []);
  expect(screen.getByText("No sales in this range")).toBeInTheDocument();
});

test("while loading, a status with a placeholder replaces the chart", () => {
  render(<TrendChart granularity={undefined} buckets={undefined} range={undefined} currency={undefined} />);

  const status = screen.getByRole("status");
  expect(status).toHaveAttribute("aria-busy", "true");
  expect(status).toHaveTextContent("Loading…");
  expect(status.querySelector(".animate-pulse.motion-reduce\\:animate-none.h-72")).not.toBeNull();
  expect(screen.queryByText("No sales in this range")).not.toBeInTheDocument();
});

test("the word revenue appears nowhere", () => {
  renderChart("daily", [{ bucket_start: "2025-03-01", gross_sales: "1.0000" }]);
  expect(document.body).not.toHaveTextContent(/revenue/i);
});

test("bucket labels come from the date text in UTC, never the local zone", () => {
  expect(bucketLabel("2025-03-01", "daily")).toBe("1 Mar");
  expect(bucketLabel("2025-03-01", "monthly")).toBe("Mar 2025");
  expect(bucketLabel("2025-01-01", "monthly")).toBe("Jan 2025");
  expect(bucketLabel("2025-03-03", "weekly")).toBe("Week of 3 Mar");
  expect(bucketLabel("2024-12-31", "daily")).toBe("31 Dec");
  expect(bucketLabel("2025-03-05", "daily")).toBe("5 Mar");
});

test("tooltip labels carry the year", () => {
  expect(bucketLabelWithYear("2025-03-05", "daily")).toBe("5 Mar 2025");
  expect(bucketLabelWithYear("2025-03-03", "weekly")).toBe("Week of 3 Mar 2025");
  expect(bucketLabelWithYear("2025-03-01", "monthly")).toBe("Mar 2025");
});

test("a text that is not a date is shown as received", () => {
  expect(parseBucketDate("2025-03-01")?.toISOString()).toBe("2025-03-01T00:00:00.000Z");
  expect(parseBucketDate("2025-13-45")).toBeNull();
  expect(parseBucketDate("March")).toBeNull();
  expect(bucketLabel("March", "daily")).toBe("March");
  expect(bucketLabelWithYear("", "weekly")).toBe("");
});

test("axis money is shortened on large values and keeps the currency", () => {
  expect(formatMoneyShort(0, "USD")).toBe("$0");
  expect(formatMoneyShort(950, "USD")).toBe("$950");
  expect(formatMoneyShort(12345, "USD")).toBe("$12K");
  expect(formatMoneyShort(1234567, "USD")).toBe("$1.2M");
  expect(formatMoneyShort(12345, "EUR")).toBe("€12K");
  expect(formatMoneyShort(5, "NOPE")).toBe("5 NOPE");
});

test("the range sentence names granularity and both dates", () => {
  expect(rangeSentence("daily", range)).toBe("Daily gross sales from 2025-03-01 to 2025-03-31");
  expect(rangeSentence("monthly", { start: "2023-01-01", end: "2025-06-30" })).toBe(
    "Monthly gross sales from 2023-01-01 to 2025-06-30",
  );
});

test("focusing a point shows its date with the year and its gross sales in full", () => {
  const { container } = renderChart("weekly", [
    { bucket_start: "2025-03-03", gross_sales: "1234.5678" },
    { bucket_start: "2025-03-10", gross_sales: "20.0000" },
  ]);

  // Keyboard: focusing the chart shows the first point, the arrow keys step on. (Hover uses the same tooltip.)
  const surface = container.querySelector(".recharts-surface") as SVGElement;
  fireEvent.focus(surface);

  const tooltip = container.querySelector(".recharts-tooltip-wrapper") as HTMLElement;
  expect(tooltip).toHaveTextContent("Week of 3 Mar 2025");
  expect(tooltip).toHaveTextContent("Gross sales : $1,234.57");

  fireEvent.keyDown(surface, { key: "ArrowRight" });
  expect(tooltip).toHaveTextContent("Week of 10 Mar 2025");
  expect(tooltip).toHaveTextContent("Gross sales : $20.00");
});
