import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { ApiError } from "./lib/api";
import type { Created, Meta, Summary } from "./lib/types";

// The whole screen flow (upload screen, then dashboard) with the api stubbed:
// what a keyboard or screen-reader user meets, in the order they meet it.
const { sample, getMeta, getAnalytics, remove, config } = vi.hoisted(() => ({
  sample: vi.fn(),
  config: vi.fn(),
  getMeta: vi.fn(),
  getAnalytics: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("./lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./lib/api")>()),
  createSampleDataset: sample,
  getConfig: config,
  getMeta,
  getAnalytics,
  deleteDataset: remove,
}));

const meta: Meta = {
  id: "d1",
  currency: "USD",
  created_at: "2026-09-30T12:00:00Z",
  expires_at: "2026-10-01T12:00:00Z",
  row_count: 90,
  date_range: { min: "2025-01-01", max: "2025-03-31" },
};

const full: Summary = {
  range: { start: "2025-01-01", end: "2025-03-31" },
  currency: "USD",
  granularity: "monthly",
  kpis: { gross_sales: "300.0000", orders: 3, units_sold: 6, average_order_value: "100.0000" },
  trend: [
    { bucket_start: "2025-01-01", gross_sales: "100.0000" },
    { bucket_start: "2025-02-01", gross_sales: "100.0000" },
    { bucket_start: "2025-03-01", gross_sales: "100.0000" },
  ],
  top_products: [
    { product_id: "p1", product_name: "Desk", gross_sales: "200.0000", units_sold: 4, distinct_orders: 2 },
  ],
};

const narrow: Summary = {
  range: { start: "2025-01-15", end: "2025-03-31" },
  currency: "USD",
  granularity: "monthly",
  kpis: { gross_sales: "250.0000", orders: 2, units_sold: 5, average_order_value: "125.0000" },
  trend: [
    { bucket_start: "2025-01-01", gross_sales: "50.0000" },
    { bucket_start: "2025-02-01", gross_sales: "100.0000" },
    { bucket_start: "2025-03-01", gross_sales: "100.0000" },
  ],
  top_products: [
    { product_id: "p1", product_name: "Desk", gross_sales: "150.0000", units_sold: 3, distinct_orders: 1 },
  ],
};

function created(): Created {
  return { dataset_id: "d1", token: "secret-token", meta, warnings: [], initial_summary: full };
}

beforeEach(() => {
  config.mockResolvedValue({ public_demo_mode: false, max_upload_bytes: 52428800, max_rows: 500000 });
  getMeta.mockResolvedValue(meta);
  getAnalytics.mockImplementation((_id: string, range: { start?: string; end?: string }) =>
    Promise.resolve(range.start === "2025-01-15" ? narrow : full),
  );
  remove.mockResolvedValue(undefined);
  sample.mockResolvedValue(created());
});

afterEach(() => {
  cleanup();
  for (const mock of [sample, config, getMeta, getAnalytics, remove]) mock.mockReset();
  window.sessionStorage.clear();
});

function renderApp(path = "/") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// What Tab reaches, in document order: enabled, visible controls without
// tabindex="-1". jsdom has no layout, so this is the DOM-order approximation.
function tabStops(): string[] {
  const selector = "a[href], button, input, select, textarea, [tabindex]";
  return Array.from(document.querySelectorAll<HTMLElement>(selector))
    .filter((el) => !el.hasAttribute("disabled") && el.getAttribute("tabindex") !== "-1")
    .map((el) => {
      if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement) {
        return el.labels?.[0]?.textContent ?? "";
      }
      return el.textContent ?? "";
    });
}

function focusEach() {
  for (const el of document.querySelectorAll<HTMLElement>("a[href], button, input, select")) {
    if (el.hasAttribute("disabled")) continue;
    el.focus();
    expect(document.activeElement).toBe(el);
  }
}

test("upload screen: every control has a visible label or name and no tab stop is hidden or forced", async () => {
  renderApp("/");
  await screen.findByLabelText("CSV file");

  expect(screen.getByLabelText("CSV file")).toHaveAttribute("type", "file");
  expect(screen.getByLabelText("Currency").tagName).toBe("SELECT");
  expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try sample data" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download sample CSV" })).toHaveAttribute("href", "/api/sample.csv");
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Open Sales Analytics");
  expect(document.querySelectorAll("h1")).toHaveLength(1);
  for (const section of ["File format", "Start an analysis"]) {
    expect(screen.getByRole("region", { name: section })).toBeInTheDocument();
  }
  expect(document.querySelector("[tabindex]:not([tabindex='-1'])")).toBeNull();
});

test("upload screen: keyboard order is sample link, file, currency, then Upload once it is enabled, then Try sample data", async () => {
  renderApp("/");
  await screen.findByLabelText("CSV file");

  // Upload is disabled, so Tab skips it
  expect(tabStops()).toEqual(["Download sample CSV", "CSV file", "Currency", "Try sample data"]);
  focusEach();

  fireEvent.change(screen.getByLabelText("CSV file"), {
    target: { files: [new File(["a"], "sales.csv", { type: "text/csv" })] },
  });
  fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USD" } });

  expect(tabStops()).toEqual(["Download sample CSV", "CSV file", "Currency", "Upload", "Try sample data"]);
  focusEach();
});

test("demo upload screen: no form controls, one h1, link and Try sample data are labelled keyboard stops", async () => {
  config.mockResolvedValue({ public_demo_mode: true, max_upload_bytes: 52428800, max_rows: 500000 });
  renderApp("/");
  await screen.findByRole("link", { name: "Run it yourself with Docker" });

  expect(screen.queryByLabelText("CSV file")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Currency")).not.toBeInTheDocument();
  expect(document.querySelectorAll("h1")).toHaveLength(1);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Open Sales Analytics");
  for (const section of ["File format", "Start an analysis"]) {
    expect(screen.getByRole("region", { name: section })).toBeInTheDocument();
  }
  expect(tabStops()).toEqual(["Download sample CSV", "Try sample data", "Run it yourself with Docker"]);
  expect(document.querySelector("[tabindex]:not([tabindex='-1'])")).toBeNull();
  focusEach();
});

test("upload screen: Try sample data, focused and activated, opens the dashboard", async () => {
  renderApp("/");
  const button = await screen.findByRole("button", { name: "Try sample data" });
  button.focus();
  expect(button).toHaveFocus();
  fireEvent.click(button);

  expect(await screen.findByRole("region", { name: "Date range" })).toBeInTheDocument();
  await screen.findByText("2025-01-01 to 2025-03-31");
});

async function openDashboard() {
  renderApp("/");
  fireEvent.click(await screen.findByRole("button", { name: "Try sample data" }));
  await screen.findByText("2025-01-01 to 2025-03-31");
  await screen.findByRole("img", { name: /Monthly gross sales/ });
}

test("dashboard: the labelled fields, buttons, regions and chart alternatives are all there", async () => {
  await openDashboard();

  expect(screen.getByLabelText("Start date")).toHaveValue("2025-01-01");
  expect(screen.getByLabelText("End date")).toHaveValue("2025-03-31");
  expect(screen.getByRole("button", { name: "Reset" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Analyze another file" })).toBeInTheDocument();
  for (const name of ["Date range", "Key figures", "Sales trend", "Top products"]) {
    expect(screen.getByRole("region", { name })).toBeInTheDocument();
  }
  expect(document.querySelectorAll("h1")).toHaveLength(1);
  expect(screen.getByRole("img", { name: "Monthly gross sales from 2025-01-01 to 2025-03-31" })).toBeInTheDocument();
  const products = within(screen.getByRole("region", { name: "Top products" }));
  expect(products.getByRole("img", { name: /^Top 1 product/ })).toBeInTheDocument();
  expect(products.getByRole("table")).toBeInTheDocument();
  for (const term of ["Gross sales", "Orders", "Units sold", "Average order value"]) {
    expect(within(screen.getByRole("region", { name: "Key figures" })).getByText(term)).toBeInTheDocument();
  }
  expect(document.body.textContent).not.toMatch(/revenue/i);
});

test("dashboard: keyboard order is Analyze another file, the dates, then Reset once the range is narrowed", async () => {
  await openDashboard();

  // Success notice first (its Dismiss), then the page controls; Reset is disabled at the full range
  const stops = tabStops();
  expect(stops.slice(0, 2)).toEqual(["Dismiss", "Analyze another file"]);
  expect(stops.slice(2, 4)).toEqual(["Start date", "End date"]);
  expect(stops).not.toContain("Reset");

  const start = screen.getByLabelText("Start date");
  start.focus();
  expect(start).toHaveFocus();
  fireEvent.change(start, { target: { value: "2025-01-15" } });

  expect(await screen.findByText("$250.00")).toBeInTheDocument();
  expect(tabStops().slice(2, 5)).toEqual(["Start date", "End date", "Reset"]);
  focusEach();

  const reset = screen.getByRole("button", { name: "Reset" });
  reset.focus();
  fireEvent.click(reset);
  expect(await screen.findByText("$300.00")).toBeInTheDocument();
  expect(start).toHaveValue("2025-01-01");
  expect(screen.getByRole("button", { name: "Reset" })).toBeDisabled();
});

test("dashboard: a range the dataset does not cover is an alert tied to its field, and nothing is applied", async () => {
  await openDashboard();
  const calls = getAnalytics.mock.calls.length;

  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2024-12-01" } });

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Start date must be between 2025-01-01 and 2025-03-31");
  expect(screen.getByLabelText("Start date")).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByLabelText("Start date")).toHaveAccessibleDescription(
    "Start date must be between 2025-01-01 and 2025-03-31",
  );
  expect(screen.getByLabelText("End date")).not.toHaveAttribute("aria-invalid");
  expect(getAnalytics).toHaveBeenCalledTimes(calls);
  expect(screen.getByText("$300.00")).toBeInTheDocument();
});

test("dashboard: the partial-month note and the text alternative reach a screen reader", async () => {
  await openDashboard();
  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2025-01-15" } });

  const trend = within(screen.getByRole("region", { name: "Sales trend" }));
  await waitFor(() =>
    expect(trend.getByRole("img", { name: "Monthly gross sales from 2025-01-15 to 2025-03-31" })).toBeInTheDocument(),
  );
  expect(trend.getByText(/^Partial period:/)).toBeInTheDocument();
});

test("dashboard: Success is a status, a failure is an alert with a Retry that can be focused and used", async () => {
  getAnalytics.mockRejectedValueOnce(new ApiError(500, "internal_error", "boom"));
  renderApp("/");
  fireEvent.click(await screen.findByRole("button", { name: "Try sample data" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Something went wrong loading this data");
  expect(screen.getAllByRole("status").some((el) => el.textContent?.includes("Success"))).toBe(true);
  const retry = within(alert).getByRole("button", { name: "Retry" });
  retry.focus();
  expect(retry).toHaveFocus();
  fireEvent.click(retry);

  expect(await screen.findByText("$300.00")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("full-page states keep the h1 and give one focusable way out", async () => {
  renderApp("/d/d1");

  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Open Sales Analytics");
  expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
  const way = screen.getByRole("link");
  way.focus();
  expect(way).toHaveFocus();
  expect(tabStops()).toHaveLength(1);
});
