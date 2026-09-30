import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "./App";
import { readSession, saveSession } from "./lib/session";
import type { Created, Issue } from "./lib/types";

const { sample, getMeta, remove, config } = vi.hoisted(() => ({
  sample: vi.fn(),
  config: vi.fn(),
  getMeta: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("./lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./lib/api")>()),
  createSampleDataset: sample,
  getConfig: config,
  getMeta,
  deleteDataset: remove,
}));

const meta = {
  id: "d1",
  currency: "USD",
  created_at: "2026-09-30T12:00:00Z",
  expires_at: "2026-10-01T12:00:00Z",
  row_count: 1200,
  date_range: { min: "2025-01-01", max: "2025-03-31" },
};

function created(warnings: Issue[] = []): Created {
  return {
    dataset_id: "d1",
    token: "secret-token",
    meta,
    warnings,
    initial_summary: {
      range: { start: "2025-01-01", end: "2025-03-31" },
      currency: "USD",
      granularity: "daily",
      kpis: { gross_sales: "1.0000", orders: 1, units_sold: 1, average_order_value: "1.0000" },
      trend: [],
      top_products: [],
    },
  };
}

beforeEach(() => {
  config.mockResolvedValue({ public_demo_mode: false, max_upload_bytes: 52428800, max_rows: 500000 });
  getMeta.mockResolvedValue(meta);
  remove.mockResolvedValue(undefined);
  sample.mockResolvedValue(created());
});

afterEach(() => {
  cleanup();
  sample.mockReset();
  config.mockReset();
  getMeta.mockReset();
  remove.mockReset();
  window.sessionStorage.clear();
});

function Where() {
  const location = useLocation();
  return (
    <p data-testid="where">
      {location.pathname}|{location.search}|{location.hash}|{JSON.stringify(location.state)}
    </p>
  );
}

function renderApp(path = "/") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const where = () => screen.getByTestId("where").textContent;

test("/ renders the upload screen with the product name", () => {
  renderApp("/");

  expect(screen.getByRole("heading", { level: 1, name: "Open Sales Analytics" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try sample data" })).toBeInTheDocument();
});

test("a successful load goes to /d/<id> with nothing else in the URL or router state", async () => {
  renderApp("/");

  fireEvent.click(screen.getByRole("button", { name: "Try sample data" }));

  expect(await screen.findByText("2025-01-01 to 2025-03-31")).toBeInTheDocument();
  expect(where()).toBe("/d/d1|||null");
  expect(screen.getByText("1,200")).toBeInTheDocument();
  expect(readSession()).toEqual({ id: "d1", token: "secret-token" });
  expect(screen.queryByRole("button", { name: "Dismiss notice" })).not.toBeInTheDocument();
});

test("warnings from creation show in a notice that can be dismissed", async () => {
  sample.mockResolvedValue(
    created([{ code: "zero_price", reason: "3 lines have a unit price of 0.", row_number: null, field: null }]),
  );
  renderApp("/");

  fireEvent.click(screen.getByRole("button", { name: "Try sample data" }));

  expect(await screen.findByText("3 lines have a unit price of 0.")).toBeInTheDocument();
  expect(where()).toBe("/d/d1|||null");
  fireEvent.click(screen.getByRole("button", { name: "Dismiss notice" }));
  expect(screen.queryByText("3 lines have a unit price of 0.")).not.toBeInTheDocument();
});

test("a reload (a fresh app at the same URL) shows the dashboard but not the notice", async () => {
  sample.mockResolvedValue(
    created([{ code: "zero_price", reason: "3 lines have a unit price of 0.", row_number: null, field: null }]),
  );
  renderApp("/");
  fireEvent.click(screen.getByRole("button", { name: "Try sample data" }));
  await screen.findByText("3 lines have a unit price of 0.");
  cleanup();

  renderApp("/d/d1");

  expect(await screen.findByText("2025-01-01 to 2025-03-31")).toBeInTheDocument();
  expect(screen.queryByText("3 lines have a unit price of 0.")).not.toBeInTheDocument();
  expect(window.sessionStorage.getItem("osa.session")).not.toContain("unit price");
});

test("opening / while a dataset is stored shows the upload screen without redirecting", () => {
  saveSession({ id: "d1", token: "tok" });
  renderApp("/");

  expect(screen.getByRole("button", { name: "Try sample data" })).toBeInTheDocument();
  expect(where()).toBe("/|||null");
  expect(getMeta).not.toHaveBeenCalled();
});

test("an unknown path goes to /", async () => {
  renderApp("/nope/at/all");

  await waitFor(() => expect(where()).toBe("/|||null"));
  expect(screen.getByRole("button", { name: "Try sample data" })).toBeInTheDocument();
});

test("/d/<id> without a stored token shows the message and sends no request", () => {
  renderApp("/d/d1");

  expect(screen.getByText(/cannot be opened from this browser session/)).toBeInTheDocument();
  expect(getMeta).not.toHaveBeenCalled();
});

test("Analyze another file returns to the upload screen and the dataset is gone", async () => {
  renderApp("/");
  fireEvent.click(screen.getByRole("button", { name: "Try sample data" }));
  await screen.findByText("2025-01-01 to 2025-03-31");

  fireEvent.click(screen.getByRole("button", { name: "Analyze another file" }));

  expect(await screen.findByRole("button", { name: "Try sample data" })).toBeInTheDocument();
  expect(where()).toBe("/|||null");
  expect(remove).toHaveBeenCalledWith("d1");
  expect(readSession()).toBeNull();
});
