import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";
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
  // 12:19 UTC is 08:19 in New York, in English day-first form
  expect(within(region).getByText(/^30 Sep 2026, 08:19/)).toBeInTheDocument();
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

  expect(await screen.findByText(/^30 Sep 2026, 22:30/)).toBeInTheDocument();
  expect(screen.getByText("2025-03-01 to 2025-03-01")).toBeInTheDocument();
});

describe("Expires fact (#42)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  test("relative time is the primary text, the exact local time is secondary and the tooltip", async () => {
    // Fixed clock, no sleeping: 23 hours before the 12:19:11Z expiry.
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-09-29T13:19:11Z") });
    renderAt("/d/d1");

    const primary = await screen.findByText("Expires in 23 hours");
    expect(primary).toHaveAttribute("title", expect.stringMatching(/^30 Sep 2026, 08:19/));
    const fact = primary.closest("dd") as HTMLElement;
    expect(fact.lastElementChild).toHaveTextContent(/^30 Sep 2026, 08:19/);
    expect(fact.firstElementChild).toBe(primary);
  });

  test("text does not depend on the browser's Turkish locale", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-09-29T13:19:11Z") });
    const language = vi.spyOn(window.navigator, "language", "get").mockReturnValue("tr-TR");
    const languages = vi.spyOn(window.navigator, "languages", "get").mockReturnValue(["tr-TR", "tr"]);
    const browserLocale = vi.spyOn(Date.prototype, "toLocaleString");
    renderAt("/d/d1");

    expect(await screen.findByText("Expires in 23 hours")).toBeInTheDocument();
    expect(screen.getByText(/^30 Sep 2026, 08:19/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Eyl|Ekim|saat|GMT-4.*Eyl/);
    expect(browserLocale).not.toHaveBeenCalled();
    expect(language).toBeDefined();
    expect(languages).toBeDefined();
  });
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

// ---- Expired, unauthorized, empty and error states (#32) ----

const NOT_FOUND = () => new ApiError(404, "not_found", "The dataset was not found.");
const UNAUTHORIZED = () => new ApiError(401, "unauthorized", "A valid bearer token is required.");
const INTERNAL = () => new ApiError(500, "internal_error", "Something went wrong on the server.");
const NETWORK = () => new ApiError(0, "network_error", "The server could not be reached.");
const INVALID_RANGE = () => new ApiError(400, "invalid_range", "start must not be after end.");

function expectExpiredCard() {
  const card = screen.getByRole("alert");
  expect(within(card).getByRole("heading", { level: 2, name: "This dataset has expired or was deleted" })).toBeInTheDocument();
  expect(card).toHaveTextContent("Upload a file or try the sample data again.");
  expect(within(card).getByRole("link", { name: "Go to the upload screen" })).toHaveAttribute("href", "/");
  expect(screen.getByRole("heading", { level: 1, name: "Open Sales Analytics" })).toBeInTheDocument();
  expect(screen.queryByRole("region")).not.toBeInTheDocument();
  expect(screen.queryByText("€1,234,567.89")).not.toBeInTheDocument();
}

const cachedAnalytics = () =>
  queryClient
    .getQueryCache()
    .getAll()
    .filter(
      (query) =>
        (query.queryKey[0] === "analytics" || query.queryKey[0] === "meta") &&
        (query.state.data !== undefined || query.state.error !== null),
    );

test("a 404 from the metadata shows the expired card, clears the session and the cache", async () => {
  getMeta.mockRejectedValue(NOT_FOUND());
  renderAt("/d/d1");

  await screen.findByRole("heading", { level: 2, name: "This dataset has expired or was deleted" });
  expectExpiredCard();
  expect(document.body.textContent).not.toMatch(/404|not_found|revenue/);
  await waitFor(() => expect(readSession()).toBeNull());
  await waitFor(() => expect(cachedAnalytics()).toHaveLength(0));
});

test("a 404 from analytics shows the expired card with none of the old numbers", async () => {
  getAnalytics.mockRejectedValue(NOT_FOUND());
  renderAt("/d/d1");

  await screen.findByRole("heading", { level: 2, name: "This dataset has expired or was deleted" });
  expectExpiredCard();
  await waitFor(() => expect(readSession()).toBeNull());
  await waitFor(() => expect(cachedAnalytics()).toHaveLength(0));
  // the card stays although the session and the cached answers are gone
  expect(screen.getByRole("alert")).toHaveTextContent("expired or was deleted");
});

test("a 401 from analytics shows the cannot-be-opened card and clears the session", async () => {
  getAnalytics.mockRejectedValue(UNAUTHORIZED());
  renderAt("/d/d1");

  const card = await screen.findByRole("alert");
  expect(within(card).getByRole("heading", { level: 2 })).toHaveTextContent(
    "This dataset cannot be opened from this browser session",
  );
  expect(within(card).getByRole("link", { name: "Go to the upload screen" })).toHaveAttribute("href", "/");
  expect(screen.queryByText(/expired/)).not.toBeInTheDocument();
  await waitFor(() => expect(readSession()).toBeNull());
  await waitFor(() => expect(cachedAnalytics()).toHaveLength(0));
});

test("a 401 from the metadata also clears this dataset's session", async () => {
  getMeta.mockRejectedValue(UNAUTHORIZED());
  renderAt("/d/d1");

  await screen.findByText(/cannot be opened from this browser session/);
  await waitFor(() => expect(readSession()).toBeNull());
});

test("a stored session of another dataset is never cleared by this page's 404", async () => {
  getMeta.mockRejectedValue(NOT_FOUND());
  renderAt("/d/d1");
  // the session moved to another dataset while the request was running
  saveSession({ id: "other", token: "other-token" });

  await screen.findByRole("heading", { level: 2, name: "This dataset has expired or was deleted" });
  await waitFor(() => expect(cachedAnalytics()).toHaveLength(0));
  expect(readSession()).toEqual({ id: "other", token: "other-token" });
});

test("Back to the dataset after a 404 shows the no-session card and no old numbers", async () => {
  const view = renderAt("/d/d1");
  await screen.findByText("10,482");
  // the dataset expires: the next request is answered 404
  getAnalytics.mockRejectedValue(NOT_FOUND());
  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2025-03-10" } });
  await screen.findByRole("heading", { level: 2, name: "This dataset has expired or was deleted" });
  await waitFor(() => expect(readSession()).toBeNull());
  view.unmount();
  getMeta.mockClear();
  getAnalytics.mockClear();

  renderAt("/d/d1");

  expect(screen.getByText(/cannot be opened from this browser session/)).toBeInTheDocument();
  expect(screen.queryByText("10,482")).not.toBeInTheDocument();
  expect(getMeta).not.toHaveBeenCalled();
  expect(getAnalytics).not.toHaveBeenCalled();
});

test("a dashboard open when the dataset expires shows the expired card on a range change, old numbers gone", async () => {
  await renderLoaded();
  answerEvery(7);
  fireEvent.change(filterInputs().start, { target: { value: "2025-03-10" } });
  await screen.findByText("Product 7");

  getAnalytics.mockRejectedValue(NOT_FOUND());
  // a range already viewed comes from the cache: no request, the numbers stay
  fireEvent.click(filterInputs().reset);
  expect(await screen.findByText("10,482")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { level: 2, name: /expired/ })).not.toBeInTheDocument();

  // a range not yet viewed makes a request: the card replaces everything
  fireEvent.change(filterInputs().start, { target: { value: "2025-03-12" } });

  await screen.findByRole("heading", { level: 2, name: "This dataset has expired or was deleted" });
  expectExpiredCard();
  expect(screen.queryByText("10,482")).not.toBeInTheDocument();
  expect(screen.queryByText(/Product/)).not.toBeInTheDocument();
  await waitFor(() => expect(readSession()).toBeNull());
});

test("a dashboard open when the dataset expires shows the expired card on Retry", async () => {
  getAnalytics.mockRejectedValueOnce(INTERNAL());
  renderAt("/d/d1");
  await screen.findByRole("button", { name: "Retry" });
  getAnalytics.mockRejectedValue(NOT_FOUND());

  fireEvent.click(screen.getByRole("button", { name: "Retry" }));

  await screen.findByRole("heading", { level: 2, name: "This dataset has expired or was deleted" });
  expectExpiredCard();
});

test("a 5xx from analytics shows one error block in Key figures with Retry, and nothing else in the other sections", async () => {
  getAnalytics.mockRejectedValue(INTERNAL());
  renderAt("/d/d1");

  const keyFigures = screen.getByRole("region", { name: "Key figures" });
  const alert = await within(keyFigures).findByRole("alert");
  expect(alert).toHaveTextContent("Something went wrong loading this data");
  expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/500|internal_error|Something went wrong on the server/);
  expect(within(keyFigures).queryByRole("status")).not.toBeInTheDocument();
  for (const name of ["Sales trend", "Top products"]) {
    const region = screen.getByRole("region", { name });
    expect(region).toBeEmptyDOMElement();
  }
  expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
  // the date filter stays usable and the metadata shows
  await screen.findByText("2025-03-01 to 2025-03-31");
  expect(filterInputs().start).toBeEnabled();
  expect(screen.getAllByRole("alert")).toHaveLength(1);
});

test("Retry repeats the request and the data replaces the block", async () => {
  getAnalytics.mockRejectedValueOnce(INTERNAL());
  renderAt("/d/d1");
  fireEvent.click(await screen.findByRole("button", { name: "Retry" }));

  expect(await screen.findByText("10,482")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  expect(getAnalytics).toHaveBeenCalledTimes(2);
  expect(getAnalytics.mock.calls[1][1]).toEqual({ start: undefined, end: undefined });
});

test("a network failure of analytics shows the same block", async () => {
  getAnalytics.mockRejectedValue(NETWORK());
  renderAt("/d/d1");

  const alert = await within(screen.getByRole("region", { name: "Key figures" })).findByRole("alert");
  expect(alert).toHaveTextContent("Something went wrong loading this data");
  expect(alert).not.toHaveTextContent(/could not be reached|network/i);
  expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

test("a 502 with an unreadable body shows the same block", async () => {
  getAnalytics.mockRejectedValue(new ApiError(502, "unknown_error", "The server sent an unexpected response."));
  renderAt("/d/d1");

  const alert = await within(screen.getByRole("region", { name: "Key figures" })).findByRole("alert");
  expect(alert).toHaveTextContent("Something went wrong loading this data");
  expect(alert).not.toHaveTextContent(/unexpected response|unknown_error/);
});

test("changing the range after a failure starts a new request, removes the block and shows no old numbers as the new range's", async () => {
  await renderLoaded();
  getAnalytics.mockRejectedValue(INTERNAL());
  fireEvent.change(filterInputs().start, { target: { value: "2025-03-10" } });
  const keyFigures = screen.getByRole("region", { name: "Key figures" });
  await within(keyFigures).findByRole("alert");
  // the old full-range numbers are not shown beside the failed range's block
  expect(screen.queryByText("10,482")).not.toBeInTheDocument();
  expect(screen.queryByText("Updating…")).not.toBeInTheDocument();
  getAnalytics.mockClear();
  answerEvery(12);

  fireEvent.change(filterInputs().end, { target: { value: "2025-03-20" } });

  expect(await screen.findByText("12")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(getAnalytics).toHaveBeenCalledTimes(1);
  expect(getAnalytics.mock.calls[0][1]).toEqual({ start: "2025-03-10", end: "2025-03-20" });
});

test("a failed metadata with a 5xx keeps the block with Retry in the Date range card", async () => {
  getMeta.mockRejectedValueOnce(INTERNAL());
  renderAt("/d/d1");

  const region = screen.getByRole("region", { name: "Date range" });
  const alert = await within(region).findByRole("alert");
  expect(alert).toHaveTextContent("Something went wrong loading this data");
  fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
  expect(await within(region).findByText("EUR")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a network failure of the metadata shows the block in the Date range card", async () => {
  getMeta.mockRejectedValue(NETWORK());
  renderAt("/d/d1");

  const alert = await within(screen.getByRole("region", { name: "Date range" })).findByRole("alert");
  expect(alert).toHaveTextContent("Something went wrong loading this data");
  expect(alert).not.toHaveTextContent(/could not be reached/);
});

test("a 400 from analytics shows the range message with Reset, and Reset asks for the full range", async () => {
  await renderLoaded();
  getAnalytics.mockRejectedValue(INVALID_RANGE());
  fireEvent.change(filterInputs().start, { target: { value: "2025-03-10" } });

  const keyFigures = screen.getByRole("region", { name: "Key figures" });
  const alert = await within(keyFigures).findByRole("alert");
  expect(alert).toHaveTextContent("The selected date range is not valid for this dataset");
  expect(alert).not.toHaveTextContent(/start must|invalid_range|400/);
  expect(within(alert).queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Sales trend" })).toBeEmptyDOMElement();

  // the full range was viewed before, so it comes from the cache
  fireEvent.click(within(alert).getByRole("button", { name: "Reset" }));

  expect(await screen.findByText("10,482")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(filterInputs().start).toHaveValue("2025-03-01");
  expect(filterInputs().end).toHaveValue("2025-03-31");
});

test("a 400 on the full range: Reset sends the request again", async () => {
  getAnalytics.mockRejectedValueOnce(INVALID_RANGE());
  renderAt("/d/d1");
  const alert = await within(screen.getByRole("region", { name: "Key figures" })).findByRole("alert");

  fireEvent.click(within(alert).getByRole("button", { name: "Reset" }));

  expect(await screen.findByText("10,482")).toBeInTheDocument();
  expect(getAnalytics).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

const noSales: Summary = {
  ...summary,
  kpis: { gross_sales: "0.0000", orders: 0, units_sold: 0, average_order_value: "0.0000" },
  trend: [{ bucket_start: "2025-03-10", gross_sales: "0.0000" }],
  top_products: [],
};

test("a range with no sales shows the warning notice below the Date range card, zeros and the empty states", async () => {
  await renderLoaded();
  getAnalytics.mockResolvedValue({ ...noSales, range: { start: "2025-03-10", end: "2025-03-11" } });
  fireEvent.change(filterInputs().start, { target: { value: "2025-03-10" } });

  const notice = await screen.findByText("No sales in the selected range");
  const box = notice.closest('[role="status"]') as HTMLElement;
  expect(box).toHaveTextContent("Warning");
  expect(within(box).getByRole("button", { name: "Reset" })).toBeInTheDocument();
  const dateRange = screen.getByRole("region", { name: "Date range" });
  expect(dateRange.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(box.compareDocumentPosition(screen.getByRole("region", { name: "Key figures" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(dateRange.nextElementSibling).toBe(box);
  const keyFigures = screen.getByRole("region", { name: "Key figures" });
  expect(within(keyFigures).getAllByText("0")).toHaveLength(2);
  expect(within(keyFigures).getAllByText("€0.00")).toHaveLength(2);
  expect(screen.getByText("No sales in this range")).toBeInTheDocument();
  expect(screen.getByText("No products sold in this range")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("Reset in the no-sales notice puts the filter back to the full range", async () => {
  await renderLoaded();
  getAnalytics.mockResolvedValue({ ...noSales, range: { start: "2025-03-10", end: "2025-03-31" } });
  fireEvent.change(filterInputs().start, { target: { value: "2025-03-10" } });
  const notice = (await screen.findByText("No sales in the selected range")).closest('[role="status"]') as HTMLElement;

  fireEvent.click(within(notice).getByRole("button", { name: "Reset" }));

  expect(await screen.findByText("10,482")).toBeInTheDocument();
  expect(screen.queryByText("No sales in the selected range")).not.toBeInTheDocument();
  expect(filterInputs().start).toHaveValue("2025-03-01");
});

test("a range with sales shows no no-sales notice", async () => {
  await renderLoaded();
  expect(screen.queryByText("No sales in the selected range")).not.toBeInTheDocument();
});

describe("a render error in one section", () => {
  beforeEach(() => {
    // React logs the error it hands to the boundary
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("in Sales trend shows the fallback there only", async () => {
    getAnalytics.mockResolvedValue({ ...summary, trend: null });
    renderAt("/d/d1");

    const trend = screen.getByRole("region", { name: "Sales trend" });
    const alert = await within(trend).findByRole("alert");
    expect(alert).toHaveTextContent("Something went wrong showing this section");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(await screen.findByText("10,482")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByLabelText("Start date")).toBeEnabled();
    expect(within(screen.getByRole("region", { name: "Top products" })).queryByRole("alert")).not.toBeInTheDocument();
  });

  test("in Top products shows the fallback there only", async () => {
    getAnalytics.mockResolvedValue({ ...summary, top_products: null });
    renderAt("/d/d1");

    const products = screen.getByRole("region", { name: "Top products" });
    expect(await within(products).findByRole("alert")).toHaveTextContent("Something went wrong showing this section");
    expect(await screen.findByText("10,482")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Sales trend" })).queryByRole("alert")).not.toBeInTheDocument();
  });

  test("in Key figures shows the fallback there only", async () => {
    getAnalytics.mockResolvedValue({ ...summary, kpis: { ...summary.kpis, units_sold: Symbol("unreadable") } });
    renderAt("/d/d1");

    const keyFigures = screen.getByRole("region", { name: "Key figures" });
    expect(await within(keyFigures).findByRole("alert")).toHaveTextContent("Something went wrong showing this section");
    expect(screen.getAllByRole("alert").length).toBeGreaterThanOrEqual(1);
    expect(within(screen.getByRole("region", { name: "Date range" })).queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Start date")).toBeEnabled();
  });

  test("in Date range shows the fallback there only", async () => {
    getMeta.mockResolvedValue({ ...meta, row_count: null });
    renderAt("/d/d1");

    const dateRange = screen.getByRole("region", { name: "Date range" });
    expect(await within(dateRange).findByRole("alert")).toHaveTextContent("Something went wrong showing this section");
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("€1,234,567.89")).toBeInTheDocument();
  });

  test("the section recovers when new data arrives", async () => {
    getAnalytics.mockResolvedValueOnce({ ...summary, trend: null });
    renderAt("/d/d1");
    await within(screen.getByRole("region", { name: "Sales trend" })).findByRole("alert");
    getAnalytics.mockResolvedValue(summary);

    fireEvent.change(filterInputs().start, { target: { value: "2025-03-10" } });

    await waitFor(() =>
      expect(within(screen.getByRole("region", { name: "Sales trend" })).queryByRole("alert")).not.toBeInTheDocument(),
    );
  });
});
