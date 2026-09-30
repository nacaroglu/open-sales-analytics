import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import DashboardPage from "./DashboardPage";
import { ApiError } from "../lib/api";
import { readSession, saveSession } from "../lib/session";
import type { Issue, Meta, Summary } from "../lib/types";

const { getMeta, getAnalytics, remove } = vi.hoisted(() => ({
  getMeta: vi.fn(),
  getAnalytics: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  getMeta,
  getAnalytics,
  deleteDataset: remove,
}));

beforeAll(() => {
  // Node re-reads TZ when it is assigned, so local time is predictable.
  (globalThis as unknown as { process: { env: Record<string, string> } }).process.env.TZ =
    "America/New_York";
});

const meta: Meta = {
  id: "d1",
  currency: "EUR",
  created_at: "2026-09-29T12:19:11Z",
  expires_at: "2026-09-30T12:19:11Z",
  row_count: 1234567,
  date_range: { min: "2025-03-01", max: "2025-03-31" },
};

const summary: Summary = {
  range: { start: "2025-03-01", end: "2025-03-31" },
  currency: "EUR",
  granularity: "daily",
  kpis: { gross_sales: "1234567.8900", orders: 10482, units_sold: 25000, average_order_value: "117.7900" },
  trend: [],
  top_products: [],
};

let queryClient: QueryClient;
const dismiss = vi.fn();

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  getMeta.mockResolvedValue(meta);
  getAnalytics.mockResolvedValue(summary);
  remove.mockResolvedValue(undefined);
  saveSession({ id: "d1", token: "tok" });
});

afterEach(() => {
  cleanup();
  getMeta.mockReset();
  getAnalytics.mockReset();
  remove.mockReset();
  dismiss.mockReset();
  window.sessionStorage.clear();
});

function BackButton() {
  const navigate = useNavigate();
  return <button onClick={() => navigate(-1)}>Back</button>;
}

function renderAt(path: string, warnings: Issue[] = []) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/start", path]} initialIndex={1}>
        <BackButton />
        <Routes>
          <Route
            path="/d/:datasetId"
            element={
              <DashboardPage datasetId={path.slice(3)} warnings={warnings} onDismissWarnings={dismiss} />
            }
          />
          <Route path="*" element={<p>Upload screen route</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("loaded state shows period as received, currency, grouped rows and local expiry", async () => {
  renderAt("/d/d1");

  const region = screen.getByRole("region", { name: "Date range" });
  expect(await within(region).findByText("2025-03-01 to 2025-03-31")).toBeInTheDocument();
  expect(within(region).getByText("EUR")).toBeInTheDocument();
  expect(within(region).getByText("1,234,567")).toBeInTheDocument();
  // 12:19 UTC is 8:19 AM in New York
  expect(within(region).getByText(/Sep 30, 2026.*8:19\sAM/)).toBeInTheDocument();
  for (const label of ["Period", "Currency", "Rows", "Expires"]) {
    expect(within(region).getByText(label)).toBeInTheDocument();
  }
  expect(getMeta).toHaveBeenCalledTimes(1);
  expect(getMeta.mock.calls[0][0]).toBe("d1");
  expect(document.body.textContent).not.toMatch(/revenue/i);
  expect(document.body.textContent).not.toContain("tok");
});

test("the expiry date follows local time across midnight, dates are never shifted", async () => {
  getMeta.mockResolvedValue({
    ...meta,
    expires_at: "2026-10-01T02:30:00Z",
    date_range: { min: "2025-03-01", max: "2025-03-01" },
  });
  renderAt("/d/d1");

  expect(await screen.findByText(/Sep 30, 2026.*10:30\sPM/)).toBeInTheDocument();
  expect(screen.getByText("2025-03-01 to 2025-03-01")).toBeInTheDocument();
});

test("the four regions exist and the h1 is the product name", async () => {
  renderAt("/d/d1");

  await screen.findByText("EUR");
  for (const name of ["Key figures", "Sales trend", "Top products", "Date range"]) {
    expect(screen.getByRole("region", { name })).toBeInTheDocument();
  }
  expect(screen.getByRole("heading", { level: 1, name: "Open Sales Analytics" })).toBeInTheDocument();
});

test("while loading, a status with Loading… replaces the facts", async () => {
  let finish: (value: Meta) => void = () => {};
  getMeta.mockReturnValue(new Promise<Meta>((resolve) => (finish = resolve)));
  renderAt("/d/d1");

  const region = screen.getByRole("region", { name: "Date range" });
  const status = within(region).getByRole("status");
  expect(status).toHaveAttribute("aria-busy", "true");
  expect(status).toHaveTextContent("Loading…");
  expect(screen.queryByText("EUR")).not.toBeInTheDocument();

  finish(meta);
  expect(await screen.findByText("EUR")).toBeInTheDocument();
  expect(within(region).queryByText("Loading…")).not.toBeInTheDocument();
});

test("no stored token: message and link to the upload screen, no request", () => {
  window.sessionStorage.clear();
  renderAt("/d/d1");

  expect(screen.getByText(/cannot be opened from this browser session/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Go to the upload screen" })).toHaveAttribute("href", "/");
  expect(getMeta).not.toHaveBeenCalled();
  expect(screen.queryByRole("region", { name: "Date range" })).not.toBeInTheDocument();
});

test("a different dataset stored: same message and the stored token is never used", () => {
  renderAt("/d/other");

  expect(screen.getByText(/cannot be opened from this browser session/)).toBeInTheDocument();
  expect(getMeta).not.toHaveBeenCalled();
  expect(remove).not.toHaveBeenCalled();
});

test("a 401 shows the same message", async () => {
  getMeta.mockRejectedValue(new ApiError(401, "unauthorized", "no"));
  renderAt("/d/d1");

  expect(await screen.findByText(/cannot be opened from this browser session/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Go to the upload screen" })).toBeInTheDocument();
});

test("another failure shows the generic error with Retry, which asks again", async () => {
  getMeta.mockRejectedValueOnce(new ApiError(500, "internal_error", "boom"));
  renderAt("/d/d1");

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong loading this data");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("EUR")).toBeInTheDocument();
  expect(getMeta).toHaveBeenCalledTimes(2);
});

test("re-rendering does not repeat the metadata request", async () => {
  const view = renderAt("/d/d1");
  await screen.findByText("EUR");
  view.rerender(<div />);
  expect(getMeta).toHaveBeenCalledTimes(1);
});

test("warnings are listed as text in a dismissible notice", async () => {
  const warnings: Issue[] = [
    { code: "zero_price", reason: "3 lines have a unit price of 0.", row_number: null, field: "unit_price" },
    { code: "extra_column", reason: "The column '<b>x</b>' is not used.", row_number: null, field: null },
  ];
  renderAt("/d/d1", warnings);

  const notice = await screen.findByRole("status");
  expect(notice).toHaveTextContent("3 lines have a unit price of 0.");
  expect(notice).toHaveTextContent("<b>x</b>");
  expect(notice.querySelector("b")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Dismiss notice" }));
  expect(dismiss).toHaveBeenCalledTimes(1);
});

test("no notice without warnings", async () => {
  renderAt("/d/d1");
  await screen.findByText("EUR");
  expect(screen.queryByRole("button", { name: "Dismiss notice" })).not.toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("Analyze another file deletes, clears the session, discards the cache and goes to /", async () => {
  queryClient.setQueryData(["analytics", "d1", undefined, undefined], { old: true });
  renderAt("/d/d1");
  await screen.findByText("EUR");

  fireEvent.click(screen.getByRole("button", { name: "Analyze another file" }));

  expect(await screen.findByText("Upload screen route")).toBeInTheDocument();
  expect(remove).toHaveBeenCalledTimes(1);
  expect(remove.mock.calls[0][0]).toBe("d1");
  expect(readSession()).toBeNull();
  expect(queryClient.getQueryData(["meta", "d1"])).toBeUndefined();
  expect(queryClient.getQueryData(["analytics", "d1", undefined, undefined])).toBeUndefined();
  expect(dismiss).toHaveBeenCalled();
});

test("Analyze another file still leaves when the delete fails", async () => {
  remove.mockRejectedValue(new ApiError(500, "internal_error", "boom"));
  renderAt("/d/d1");
  await screen.findByText("EUR");

  fireEvent.click(screen.getByRole("button", { name: "Analyze another file" }));

  expect(await screen.findByText("Upload screen route")).toBeInTheDocument();
  expect(readSession()).toBeNull();
  expect(queryClient.getQueryData(["meta", "d1"])).toBeUndefined();
});

test("Back after Analyze another file shows the no-token message and no old data", async () => {
  renderAt("/d/d1");
  await screen.findByText("EUR");
  fireEvent.click(screen.getByRole("button", { name: "Analyze another file" }));
  await screen.findByText("Upload screen route");
  getMeta.mockClear();

  fireEvent.click(screen.getByRole("button", { name: "Back" }));

  await waitFor(() =>
    expect(screen.getByText(/cannot be opened from this browser session/)).toBeInTheDocument(),
  );
  expect(screen.queryByText("EUR")).not.toBeInTheDocument();
  expect(getMeta).not.toHaveBeenCalled();
});

test("Analyze another file cannot be pressed twice", async () => {
  let finish: () => void = () => {};
  remove.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
  renderAt("/d/d1");
  await screen.findByText("EUR");
  const button = screen.getByRole("button", { name: "Analyze another file" });

  fireEvent.click(button);
  fireEvent.click(button);

  expect(button).toBeDisabled();
  expect(remove).toHaveBeenCalledTimes(1);
  finish();
  await screen.findByText("Upload screen route");
});

test("key figures show the analytics of the full range in the dataset currency, from one request", async () => {
  renderAt("/d/d1");

  const region = screen.getByRole("region", { name: "Key figures" });
  expect(within(region).getByRole("status")).toHaveAttribute("aria-busy", "true");
  expect(await within(region).findByText("€1,234,567.89")).toBeInTheDocument();
  expect(within(region).getByText("10,482")).toBeInTheDocument();
  expect(within(region).getByText("25,000")).toBeInTheDocument();
  expect(within(region).getByText("€117.79")).toBeInTheDocument();
  expect(within(region).queryByRole("status")).not.toBeInTheDocument();

  expect(getAnalytics).toHaveBeenCalledTimes(1);
  expect(getAnalytics.mock.calls[0][0]).toBe("d1");
  expect(getAnalytics.mock.calls[0][1]).toEqual({ start: undefined, end: undefined });
});

test("the sales trend region shows the chart from the one analytics response", async () => {
  getAnalytics.mockResolvedValue({
    ...summary,
    granularity: "weekly",
    trend: [
      { bucket_start: "2025-02-24", gross_sales: "10.0000" },
      { bucket_start: "2025-03-03", gross_sales: "20.0000" },
    ],
  });
  renderAt("/d/d1");

  const region = screen.getByRole("region", { name: "Sales trend" });
  expect(within(region).getByRole("status")).toHaveAttribute("aria-busy", "true");
  expect(await within(region).findByRole("heading", { name: "Gross sales — weekly" })).toBeInTheDocument();
  expect(within(region).getByRole("img", { name: /^Weekly gross sales from 2025-03-01 to 2025-03-31$/ })).toBeInTheDocument();
  expect(getAnalytics).toHaveBeenCalledTimes(1);
});
