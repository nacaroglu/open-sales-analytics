import { afterEach, beforeAll, expect, test } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import TrendChart, {
  axisLabel,
  bucketCoverage,
  bucketLabel,
  bucketLabelWithYear,
  coverageLabel,
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

test("weekly: heading and a Week of label, a first week cut by the range shows its covered dates instead", () => {
  const { container } = renderChart("weekly", [
    { bucket_start: "2025-02-24", gross_sales: "10.0000" },
    { bucket_start: "2025-03-03", gross_sales: "20.0000" },
  ]);

  expect(screen.getByRole("heading", { name: "Gross sales — weekly" })).toBeInTheDocument();
  expect(xLabels(container)).toEqual(["1–2 Mar", "Week of 3 Mar"]);
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

// Partial period coverage (fixed dates, no clock).

function coverage(start: string, granularity: "daily" | "weekly" | "monthly", from: string, to: string) {
  return bucketCoverage(start, granularity, { start: from, end: to });
}

test("a first weekly bucket cut by the range start is partial and labelled with its covered dates", () => {
  // Wed 2025-12-31 starts the range; its Monday-Sunday week is 29 Dec - 4 Jan.
  const range2 = { start: "2025-12-31", end: "2026-04-01" };
  const first = bucketCoverage("2025-12-29", "weekly", range2);
  expect(first?.partial).toBe(true);
  expect(coverageLabel(first!, false)).toBe("31 Dec–4 Jan");
  expect(coverageLabel(first!, true)).toBe("31 Dec 2025–4 Jan 2026");
  expect(axisLabel("2025-12-29", "weekly", range2)).toBe("31 Dec–4 Jan");
  expect(bucketCoverage("2026-01-05", "weekly", range2)?.partial).toBe(false);
});

test("a last weekly bucket cut by the range end is partial", () => {
  const range2 = { start: "2025-01-06", end: "2025-04-02" }; // Wed
  const last = bucketCoverage("2025-03-31", "weekly", range2);
  expect(last?.partial).toBe(true);
  expect(axisLabel("2025-03-31", "weekly", range2)).toBe("31 Mar–2 Apr");
  expect(axisLabel("2025-03-24", "weekly", range2)).toBe("Week of 24 Mar");
});

test("ranges on exact week and month boundaries leave every bucket whole", () => {
  const week = { start: "2025-01-06", end: "2025-04-06" }; // Monday to Sunday
  expect(bucketCoverage("2025-01-06", "weekly", week)?.partial).toBe(false);
  expect(bucketCoverage("2025-03-31", "weekly", week)?.partial).toBe(false);
  const month = { start: "2024-01-01", end: "2025-12-31" };
  expect(bucketCoverage("2024-01-01", "monthly", month)?.partial).toBe(false);
  expect(bucketCoverage("2025-12-01", "monthly", month)?.partial).toBe(false);
  expect(axisLabel("2025-12-01", "monthly", month)).toBe("Dec 2025");
});

test("one day short of a month on either side makes it partial", () => {
  expect(coverage("2025-03-01", "monthly", "2025-03-02", "2025-05-31")?.partial).toBe(true);
  expect(coverage("2025-05-01", "monthly", "2025-03-01", "2025-05-30")?.partial).toBe(true);
  expect(coverage("2025-04-01", "monthly", "2025-03-02", "2025-05-30")?.partial).toBe(false);
});

test("monthly: a partial month shows its dates with the year, the leap day counts", () => {
  const range2 = { start: "2024-02-10", end: "2026-02-28" };
  expect(axisLabel("2024-02-01", "monthly", range2)).toBe("10–29 Feb 2024");
  expect(axisLabel("2026-02-01", "monthly", range2)).toBe("Feb 2026"); // 28 Feb 2026 is the month's last day
  expect(axisLabel("2026-02-01", "monthly", { ...range2, end: "2026-02-27" })).toBe("1–27 Feb 2026");
  expect(coverage("2026-02-01", "monthly", "2024-02-10", "2026-02-28")?.partial).toBe(false);
  expect(coverage("2024-02-01", "monthly", "2024-02-01", "2024-02-29")?.partial).toBe(false);
});

test("a one-day daily bucket is whole, a one-day slice of a week or month is partial", () => {
  expect(coverage("2025-03-05", "daily", "2025-03-05", "2025-03-05")?.partial).toBe(false);
  expect(coverage("2025-03-03", "weekly", "2025-03-05", "2025-03-05")?.partial).toBe(true);
  expect(coverage("2025-03-01", "monthly", "2025-03-05", "2025-03-05")?.partial).toBe(true);
  expect(coverageLabel(coverage("2025-03-03", "weekly", "2025-03-05", "2025-03-05")!, true)).toBe("5 Mar 2025");
  expect(axisLabel("2025-03-05", "daily", { start: "2025-03-05", end: "2025-03-05" })).toBe("5 Mar");
});

test("a range inside one week or month shows that sole bucket as partial", () => {
  expect(coverageLabel(coverage("2025-03-03", "weekly", "2025-03-04", "2025-03-06")!, false)).toBe("4–6 Mar");
  expect(coverageLabel(coverage("2025-03-01", "monthly", "2025-03-10", "2025-03-20")!, true)).toBe("10–20 Mar 2025");
});

test("a bucket entirely outside the range has no coverage", () => {
  expect(coverage("2025-04-01", "monthly", "2025-03-01", "2025-03-31")).toBeNull();
});

test("an unreadable date gives no coverage and the plain label", () => {
  expect(bucketCoverage("March", "weekly", range)).toBeNull();
  expect(axisLabel("March", "weekly", range)).toBe("March");
});

test("a partial bucket's tooltip has the year and Partial period, a whole one does not", () => {
  const range2 = { start: "2025-12-31", end: "2026-01-11" };
  const { container } = render(
    <TrendChart
      granularity="weekly"
      buckets={[
        { bucket_start: "2025-12-29", gross_sales: "10.0000" },
        { bucket_start: "2026-01-05", gross_sales: "20.0000" },
        { bucket_start: "2026-01-12", gross_sales: "5.0000" },
      ]}
      range={{ start: range2.start, end: "2026-01-18" }}
      currency="USD"
    />,
  );
  expect(screen.getByText(/Partial period: the range cuts the first or last week/)).toBeInTheDocument();
  expect(xLabels(container)[0]).toBe("31 Dec–4 Jan");

  const surface = container.querySelector(".recharts-surface") as SVGElement;
  fireEvent.focus(surface);
  const tooltip = container.querySelector(".recharts-tooltip-wrapper") as HTMLElement;
  expect(tooltip).toHaveTextContent("Week of 29 Dec 2025");
  expect(tooltip).toHaveTextContent("Partial period: 31 Dec 2025–4 Jan 2026");

  fireEvent.keyDown(surface, { key: "ArrowRight" });
  expect(tooltip).toHaveTextContent("Week of 5 Jan 2026");
  expect(tooltip).not.toHaveTextContent("Partial period");
});

test("a range of whole weeks shows no partial note and a daily chart never does", () => {
  const { unmount } = render(
    <TrendChart
      granularity="weekly"
      buckets={[{ bucket_start: "2025-03-03", gross_sales: "10.0000" }]}
      range={{ start: "2025-03-03", end: "2025-03-09" }}
      currency="USD"
    />,
  );
  expect(screen.queryByText(/Partial period/)).toBeNull();
  unmount();
  renderChart("daily", [{ bucket_start: "2025-03-01", gross_sales: "10.0000" }]);
  expect(screen.queryByText(/Partial period/)).toBeNull();
});
