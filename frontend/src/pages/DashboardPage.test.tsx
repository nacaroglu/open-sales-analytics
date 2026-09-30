import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

test("the top products region shows the products from the one analytics response", async () => {
  getAnalytics.mockResolvedValue({
    ...summary,
    top_products: [
      { product_id: "p2", product_name: "Desk", gross_sales: "900.0000", units_sold: 3, distinct_orders: 2 },
      { product_id: "p1", product_name: "Chair", gross_sales: "100.5000", units_sold: 1, distinct_orders: 1 },
    ],
  });
  renderAt("/d/d1");

  const region = screen.getByRole("region", { name: "Top products" });
  expect(within(region).getByRole("status")).toHaveAttribute("aria-busy", "true");
  expect(within(region).getByRole("heading", { level: 2, name: "Top products" })).toBeInTheDocument();
  expect(
    await within(region).findByRole("img", { name: "Top 2 products by gross sales from 2025-03-01 to 2025-03-31" }),
  ).toBeInTheDocument();
  expect(within(region).getByText("€900.00")).toBeInTheDocument();
  expect(within(region).getAllByRole("row")).toHaveLength(3);
  expect(getAnalytics).toHaveBeenCalledTimes(1);
});

// ---- Date range filter (#31) ----

function filterInputs() {
  return {
    start: screen.getByLabelText("Start date") as HTMLInputElement,
    end: screen.getByLabelText("End date") as HTMLInputElement,
    reset: screen.getByRole("button", { name: "Reset" }),
  };
}

function type(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } });
}

// An answer for one range: orders tells the responses apart, the trend and the
// products carry the same marker so the three sections can be checked together.
function answer(
  range: { start: string; end: string },
  orders: number,
  granularity: Summary["granularity"] = "daily",
): Summary {
  return {
    ...summary,
    range,
    granularity,
    kpis: { ...summary.kpis, orders },
    trend: [{ bucket_start: range.start, gross_sales: "10.0000" }],
    top_products: [
      { product_id: "p1", product_name: `Product ${orders}`, gross_sales: "10.0000", units_sold: 1, distinct_orders: 1 },
    ],
  };
}

// Answers every request with the range it asked for (a missing bound is the dataset's).
function answerEvery(orders: number) {
  getAnalytics.mockImplementation(async (_id: string, range: { start?: string; end?: string }) =>
    answer({ start: range.start ?? "2025-03-01", end: range.end ?? "2025-03-31" }, orders),
  );
}

async function renderLoaded() {
  renderAt("/d/d1");
  await screen.findByDisplayValue("2025-03-01");
  await screen.findByText("10,482");
}

test("the filter shows Start date, End date and Reset in that order, with the dataset bounds", async () => {
  await renderLoaded();

  const { start, end, reset } = filterInputs();
  expect(start).toHaveAttribute("type", "date");
  expect(end).toHaveAttribute("type", "date");
  expect(start).toHaveValue("2025-03-01");
  expect(end).toHaveValue("2025-03-31");
  for (const input of [start, end]) {
    expect(input).toHaveAttribute("min", "2025-03-01");
    expect(input).toHaveAttribute("max", "2025-03-31");
    expect(input).toBeEnabled();
  }
  expect(start.compareDocumentPosition(end) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(end.compareDocumentPosition(reset) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(reset).toBeDisabled();
  expect(getAnalytics).toHaveBeenCalledTimes(1);
});

test("while the metadata loads the inputs and Reset are disabled and empty, and no range is sent", () => {
  getMeta.mockReturnValue(new Promise<Meta>(() => {}));
  renderAt("/d/d1");

  const { start, end, reset } = filterInputs();
  expect(start).toBeDisabled();
  expect(end).toBeDisabled();
  expect(reset).toBeDisabled();
  expect(start).toHaveValue("");
  expect(end).toHaveValue("");
  expect(getAnalytics).toHaveBeenCalledTimes(1);
  expect(getAnalytics.mock.calls[0][1]).toEqual({ start: undefined, end: undefined });
});

test("when the metadata failed the inputs and Reset stay disabled and empty", async () => {
  getMeta.mockRejectedValue(new ApiError(500, "internal_error", "boom"));
  renderAt("/d/d1");

  await screen.findByRole("alert");
  const { start, end, reset } = filterInputs();
  expect(start).toBeDisabled();
  expect(end).toBeDisabled();
  expect(reset).toBeDisabled();
  expect(start).toHaveValue("");
  expect(end).toHaveValue("");
});

test("a date outside the dataset shows an inline error, sends no request and keeps the results", async () => {
  await renderLoaded();
  const { start, end } = filterInputs();

  type(start, "2025-02-28");
  const error = screen.getByText("Start date must be between 2025-03-01 and 2025-03-31");
  expect(error).toHaveAttribute("role", "alert");
  expect(start).toHaveAttribute("aria-invalid", "true");
  expect(start).toHaveAccessibleDescription(/Start date must be between 2025-03-01 and 2025-03-31/);
  expect(end).not.toHaveAttribute("aria-invalid");

  type(end, "2025-04-01");
  expect(screen.getByText("End date must be between 2025-03-01 and 2025-03-31")).toHaveAttribute("role", "alert");
  expect(end).toHaveAttribute("aria-invalid", "true");
  expect(end).toHaveAccessibleDescription(/End date must be between/);

  expect(getAnalytics).toHaveBeenCalledTimes(1);
  expect(screen.getByText("10,482")).toBeInTheDocument();

  type(start, "2025-03-05");
  type(end, "2025-03-31");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(start).not.toHaveAttribute("aria-invalid");
  expect(start).not.toHaveAttribute("aria-describedby");
});

test("start after end shows the inverted message under Start date, sends nothing, and clears when fixed", async () => {
  await renderLoaded();
  const { start, end } = filterInputs();
  answerEvery(7);

  type(end, "2025-03-10");
  await screen.findByText("Product 7");
  getAnalytics.mockClear();
  type(start, "2025-03-20");

  const error = screen.getByText("Start date must be on or before end date");
  expect(error).toHaveAttribute("role", "alert");
  expect(start).toHaveAttribute("aria-invalid", "true");
  expect(start).toHaveAccessibleDescription("Start date must be on or before end date");
  expect(end).not.toHaveAttribute("aria-invalid");
  expect(getAnalytics).not.toHaveBeenCalled();
  expect(screen.getAllByText("Product 7").length).toBeGreaterThan(0);

  type(end, "2025-03-25");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await waitFor(() => expect(getAnalytics).toHaveBeenCalledTimes(1));
  expect(getAnalytics.mock.calls[0][1]).toEqual({ start: "2025-03-20", end: "2025-03-25" });
});

test("a valid change sends exactly one request with the dates exactly as typed", async () => {
  getMeta.mockResolvedValue({ ...meta, date_range: { min: "2025-01-01", max: "2025-12-31" } });
  renderAt("/d/d1");
  await screen.findByDisplayValue("2025-01-01");
  await screen.findByText("10,482");
  const { start, end } = filterInputs();
  getAnalytics.mockImplementation(async (_id: string, range: { start: string; end: string }) =>
    answer({ start: range.start, end: range.end ?? "2025-12-31" }, 5),
  );

  type(start, "2025-03-01");
  await screen.findByText("Product 5");
  expect(getAnalytics).toHaveBeenCalledTimes(2);
  expect(getAnalytics.mock.calls[1][1]).toEqual({ start: "2025-03-01", end: undefined });

  type(end, "2025-03-31");
  await waitFor(() => expect(getAnalytics).toHaveBeenCalledTimes(3));
  expect(getAnalytics.mock.calls[2][1]).toEqual({ start: "2025-03-01", end: "2025-03-31" });
  await waitFor(() => expect(screen.queryByText("Updating…")).not.toBeInTheDocument());
  expect(getAnalytics).toHaveBeenCalledTimes(3);
});

test("start equal to end is accepted and sends a request", async () => {
  await renderLoaded();
  const { start, end } = filterInputs();
  answerEvery(3);

  type(end, "2025-03-15");
  type(start, "2025-03-15");

  await waitFor(() =>
    expect(getAnalytics.mock.calls.at(-1)?.[1]).toEqual({ start: "2025-03-15", end: "2025-03-15" }),
  );
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("the first date into Start, the last into End and Reset after a narrower range send no request", async () => {
  await renderLoaded();
  const { start, end, reset } = filterInputs();

  type(start, "2025-03-01");
  type(end, "2025-03-31");
  expect(getAnalytics).toHaveBeenCalledTimes(1);

  answerEvery(9);
  type(start, "2025-03-10");
  await screen.findByText("Product 9");
  expect(getAnalytics).toHaveBeenCalledTimes(2);

  fireEvent.click(reset);
  expect(await screen.findByText("10,482")).toBeInTheDocument();
  expect(getAnalytics).toHaveBeenCalledTimes(2);
  expect(start).toHaveValue("2025-03-01");
  expect(end).toHaveValue("2025-03-31");
  expect(queryClient.getQueryCache().getAll().map((query) => query.queryKey)).toContainEqual([
    "analytics",
    "d1",
    undefined,
    undefined,
  ]);
  expect(queryClient.getQueryCache().getAll()).toHaveLength(3);
});

test("KPI cards, trend heading and top products all show the one response of the new range", async () => {
  await renderLoaded();
  const { start } = filterInputs();
  getAnalytics.mockResolvedValue(answer({ start: "2025-03-05", end: "2025-03-31" }, 42, "weekly"));

  type(start, "2025-03-05");

  expect(await within(screen.getByRole("region", { name: "Key figures" })).findByText("42")).toBeInTheDocument();
  const trend = screen.getByRole("region", { name: "Sales trend" });
  expect(within(trend).getByRole("heading", { name: "Gross sales — weekly" })).toBeInTheDocument();
  expect(within(trend).getByText("Weekly gross sales from 2025-03-05 to 2025-03-31")).toBeInTheDocument();
  const products = screen.getByRole("region", { name: "Top products" });
  expect(within(products).getAllByText("Product 42").length).toBeGreaterThan(0);
  expect(getAnalytics).toHaveBeenCalledTimes(2);
});

test("emptying an input sends no request and shows no error; leaving it empty refills the bound", async () => {
  await renderLoaded();
  const { start, end } = filterInputs();

  type(start, "");
  expect(start).toHaveValue("");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(getAnalytics).toHaveBeenCalledTimes(1);
  fireEvent.blur(start);
  expect(start).toHaveValue("2025-03-01");

  type(end, "");
  expect(end).toHaveValue("");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  fireEvent.blur(end);
  expect(end).toHaveValue("2025-03-31");
  expect(getAnalytics).toHaveBeenCalledTimes(1);
});

test("a refilled bound is applied like a typed one", async () => {
  await renderLoaded();
  const { start, end } = filterInputs();
  answerEvery(6);

  type(start, "2025-03-10");
  await screen.findByText("Product 6");
  getAnalytics.mockClear();
  type(start, "");
  fireEvent.blur(start);

  // start is the first date again and end the last: the full range, already viewed
  expect(start).toHaveValue("2025-03-01");
  expect(end).toHaveValue("2025-03-31");
  expect(await screen.findByText("10,482")).toBeInTheDocument();
  expect(getAnalytics).not.toHaveBeenCalled();
});

test("while a new range loads the old numbers stay and Updating… shows beside Reset", async () => {
  await renderLoaded();
  const { start, reset } = filterInputs();
  let finish: (value: Summary) => void = () => {};
  getAnalytics.mockReturnValue(new Promise<Summary>((resolve) => (finish = resolve)));

  type(start, "2025-03-10");

  const updating = await screen.findByText("Updating…");
  expect(updating).toHaveAttribute("role", "status");
  expect(updating).toHaveClass("text-sm", "text-slate-600");
  expect(reset.parentElement).toContainElement(updating);
  expect(screen.getByText("10,482")).toBeInTheDocument();
  expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
  const keyFigures = screen.getByRole("region", { name: "Key figures" });
  expect(within(keyFigures).queryByRole("status")).not.toBeInTheDocument();

  finish(answer({ start: "2025-03-10", end: "2025-03-31" }, 11));
  expect((await screen.findAllByText("Product 11")).length).toBeGreaterThan(0);
  expect(screen.queryByText("Updating…")).not.toBeInTheDocument();
});

test("the first load keeps the skeletons and shows no Updating…", async () => {
  getAnalytics.mockReturnValue(new Promise<Summary>(() => {}));
  renderAt("/d/d1");

  await screen.findByDisplayValue("2025-03-01");
  expect(
    within(screen.getByRole("region", { name: "Key figures" })).getByRole("status"),
  ).toHaveAttribute("aria-busy", "true");
  expect(screen.queryByText("Updating…")).not.toBeInTheDocument();
});

test("when two ranges are chosen quickly and the first answer arrives last, the last range wins", async () => {
  await renderLoaded();
  const { start, end } = filterInputs();
  const pending: Record<string, (value: Summary) => void> = {};
  getAnalytics.mockImplementation(
    (_id: string, range: { start?: string; end?: string }) =>
      new Promise<Summary>((resolve) => (pending[`${range.start}|${range.end}`] = resolve)),
  );

  type(start, "2025-03-05");
  type(start, "2025-03-06");
  type(end, "2025-03-30");
  await waitFor(() => expect(getAnalytics).toHaveBeenCalledTimes(4));

  // answers come back in reverse order: the last range first, the first range last
  pending["2025-03-06|2025-03-30"](answer({ start: "2025-03-06", end: "2025-03-30" }, 66));
  expect((await screen.findAllByText("Product 66")).length).toBeGreaterThan(0);
  pending["2025-03-05|undefined"](answer({ start: "2025-03-05", end: "2025-03-31" }, 55));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  expect(screen.getAllByText("Product 66").length).toBeGreaterThan(0);
  expect(screen.queryByText("Product 55")).not.toBeInTheDocument();
  expect(start).toHaveValue("2025-03-06");
  expect(end).toHaveValue("2025-03-30");
  expect(screen.queryByText("Updating…")).not.toBeInTheDocument();
});

test("Reset restores both inputs and the full-range values, and clears an inline error", async () => {
  await renderLoaded();
  const { start, end, reset } = filterInputs();
  answerEvery(8);
  type(start, "2025-03-10");
  await screen.findByText("Product 8");
  expect(reset).toBeEnabled();
  type(end, "2025-03-02");
  expect(screen.getByRole("alert")).toBeInTheDocument();

  fireEvent.click(reset);

  expect(start).toHaveValue("2025-03-01");
  expect(end).toHaveValue("2025-03-31");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(await screen.findByText("10,482")).toBeInTheDocument();
  expect(reset).toBeDisabled();
});

test("Reset is enabled when only one input differs, even while it is empty", async () => {
  await renderLoaded();
  const { start, reset } = filterInputs();

  type(start, "");
  expect(reset).toBeEnabled();
  fireEvent.click(reset);
  expect(start).toHaveValue("2025-03-01");
  expect(reset).toBeDisabled();
});

test("going back to a viewed range shows its values at once and sends no request", async () => {
  await renderLoaded();
  const { start, end } = filterInputs();
  answerEvery(21);
  type(start, "2025-03-10");
  await screen.findByText("Product 21");
  type(end, "2025-03-20");
  await waitFor(() => expect(getAnalytics).toHaveBeenCalledTimes(3));
  await waitFor(() => expect(screen.queryByText("Updating…")).not.toBeInTheDocument());
  getAnalytics.mockClear();

  type(end, "2025-03-31");
  expect(screen.queryByText("Updating…")).not.toBeInTheDocument();
  type(end, "2025-03-20");
  expect(screen.queryByText("Updating…")).not.toBeInTheDocument();
  expect(screen.getAllByText("Product 21").length).toBeGreaterThan(0);
  expect(getAnalytics).not.toHaveBeenCalled();
});

test("a dataset of one day shows that day in both inputs, Reset disabled and its numbers", async () => {
  getMeta.mockResolvedValue({ ...meta, date_range: { min: "2025-03-01", max: "2025-03-01" } });
  renderAt("/d/d1");

  await screen.findByText("10,482");
  const { start, end, reset } = filterInputs();
  expect(start).toHaveValue("2025-03-01");
  expect(end).toHaveValue("2025-03-01");
  expect(start).toHaveAttribute("min", "2025-03-01");
  expect(start).toHaveAttribute("max", "2025-03-01");
  expect(reset).toBeDisabled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("the selection is not kept in the URL or in storage", async () => {
  await renderLoaded();
  const before = JSON.stringify({ ...window.sessionStorage });
  type(filterInputs().start, "2025-03-10");
  await waitFor(() => expect(getAnalytics).toHaveBeenCalledTimes(2));

  expect(JSON.stringify({ ...window.sessionStorage })).toBe(before);
  expect(window.localStorage.length).toBe(0);
  expect(window.location.search).toBe("");
});
